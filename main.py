import psycopg2
import os
from fastapi import FastAPI
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel
from typing import Optional
import uvicorn

class PostgresTaskRepository:
    def __init__(self, database_url: str = None):
        self.database_url = database_url or os.environ["DATABASE_URL"]
        self.conn = psycopg2.connect(self.database_url)

    def get_all(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM tasks")
        rows=cursor.fetchall()
        return [{"id": row[0], "title": row[1], "done": row[2]} for row in rows]
         

    def get(self, id: int):
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM tasks WHERE id=%s", (id,))
        row = cursor.fetchone()
        if row:
            return {"id": row[0], "title": row[1], "done": row[2]}
        return None

    def create(self, title: str) -> int:
        cursor = self.conn.cursor()
        cursor.execute("INSERT INTO tasks (title, done) VALUES (%s, %s) RETURNING id", (title,False))
        new_id = cursor.fetchone()[0]
        self.conn.commit()
        return new_id

    def update(self, id: int, title: Optional[str], done: Optional[bool]):
        cursor = self.conn.cursor()
        if title is not None:
            cursor.execute("UPDATE tasks SET title=%s WHERE id=%s", (title, id))
        if done is not None:
            cursor.execute("UPDATE tasks SET done=%s WHERE id=%s", (done, id))
        if cursor.rowcount == 0:
            return None
        self.conn.commit()
        return self.get(id)

    def delete(self, id: int) -> bool:
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM tasks WHERE id=%s", (id,))
        if cursor.rowcount == 0:
            return False
        self.conn.commit()
        return True


repo = PostgresTaskRepository()
app = FastAPI()

@app.get("/")
def task_API():
    return {"name": "Task API", "version": "1.0", "endpoints": ["/tasks"]}

@app.get("/Health")
def health_check():
    return {"status": "OK"}

@app.get("/tasks")
def get_tasks():
    return repo.get_all()

@app.get("/tasks/{id}")
def get_task(id: int):
    task = repo.get(id)
    if task:
        return task
    return JSONResponse(status_code=404, content={"error": f"Task {id} not found"})

class TaskCreate(BaseModel):
    title: str = ""

@app.post("/tasks")
def create_task(task: TaskCreate):
    if not task.title.strip():
        return JSONResponse(status_code=400, content={"error": "Title cannot be empty"})
    task_id = repo.create(task.title)
    content = {"message": f"Task {task_id} created", "id": task_id, "title": task.title, "done": False}
    return JSONResponse(status_code=201, content=content)

class TaskUpdate(BaseModel):
    title: Optional[str] = None
    done: Optional[bool] = None

@app.put("/tasks/{id}")
def update_task(id: int, update: TaskUpdate):
    if update.title is None and update.done is None:
        return JSONResponse(status_code=400, content={"error": "Provide a title or done value to update"})
    if update.title is not None and not update.title.strip():
        return JSONResponse(status_code=400, content={"error": "Title cannot be empty"})

    updated = repo.update(id, update.title, update.done)
    if updated is None:
        return JSONResponse(status_code=404, content={"error": f"Task {id} not found"})
    return JSONResponse(status_code=200, content={"message": f"Task {id} updated", "id": id, "title": updated["title"], "done": updated["done"]})

@app.delete("/tasks/{id}")
def delete_task(id: int):
    deleted = repo.delete(id)
    if not deleted:
        return JSONResponse(status_code=404, content={"error": f"Task {id} not found"})
    return Response(status_code=204)
