"""WebSocket endpoint for real-time updates."""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import Set
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'src'))

from database.db_client import DatabaseClient

router = APIRouter()

# Store active WebSocket connections
active_connections: Set[WebSocket] = set()


class ConnectionManager:
    """Manage WebSocket connections."""
    
    def __init__(self):
        self.active_connections: Set[WebSocket] = set()
    
    async def connect(self, websocket: WebSocket):
        """Accept new connection."""
        await websocket.accept()
        self.active_connections.add(websocket)
        print(f"✓ WebSocket connected. Total: {len(self.active_connections)}")
    
    def disconnect(self, websocket: WebSocket):
        """Remove connection."""
        self.active_connections.discard(websocket)
        print(f"✗ WebSocket disconnected. Total: {len(self.active_connections)}")
    
    async def broadcast(self, message: dict):
        """Broadcast message to all connected clients."""
        disconnected = set()
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                print(f"Error sending to client: {e}")
                disconnected.add(connection)
        
        # Remove disconnected clients
        for conn in disconnected:
            self.disconnect(conn)


manager = ConnectionManager()


async def poll_job_updates():
    """Poll database for job updates and broadcast to clients."""
    last_update_times = {}

    while True:
        try:
            if not manager.active_connections:
                await asyncio.sleep(2)
                continue

            # Create fresh database instance for EACH poll to avoid connection timeouts
            db = None
            try:
                db = DatabaseClient()
                with db.conn.cursor() as cur:
                    # Get active jobs (queued or processing)
                    cur.execute("""
                        SELECT
                            id, status, progress, current_step, updated_at,
                            filename, doc_id, error_message
                        FROM jobs
                        WHERE status IN ('queued', 'processing')
                        ORDER BY updated_at DESC
                    """)

                    for row in cur.fetchall():
                        job_id = row[0]
                        updated_at = row[4]

                        # Only send if this is a new update
                        if job_id not in last_update_times or last_update_times[job_id] != updated_at:
                            last_update_times[job_id] = updated_at

                            message = {
                                "type": "job_update",
                                "job_id": job_id,
                                "status": row[1],
                                "progress": row[2],
                                "current_step": row[3],
                                "filename": row[5],
                                "doc_id": row[6],
                                "error_message": row[7]
                            }

                            await manager.broadcast(message)

                    # Clean up old entries from last_update_times
                    if len(last_update_times) > 1000:
                        last_update_times.clear()

            finally:
                # IMPORTANT: Always close the connection
                if db and db.conn:
                    db.conn.close()

            await asyncio.sleep(1)  # Poll every second

        except Exception as e:
            print(f"⚠️  Error in poll_job_updates: {e}")
            await asyncio.sleep(5)


@router.websocket("/jobs")
async def websocket_jobs(websocket: WebSocket):
    """
    WebSocket endpoint for real-time job updates.

    Clients connect to this endpoint to receive live updates about job progress.

    Message format:
    {
        "type": "job_update",
        "job_id": "...",
        "status": "processing",
        "progress": 45,
        "current_step": "processing_images",
        "filename": "document.pdf",
        "doc_id": "doc_123",
        "error_message": null
    }
    """
    await manager.connect(websocket)

    # Start keep-alive task
    async def send_keepalive():
        """Send periodic ping to keep connection alive."""
        while True:
            try:
                await asyncio.sleep(30)  # Ping every 30 seconds
                if websocket in manager.active_connections:
                    await websocket.send_json({"type": "ping"})
            except:
                break

    keepalive_task = asyncio.create_task(send_keepalive())

    try:
        # Send initial connection confirmation
        await websocket.send_json({
            "type": "connected",
            "message": "Connected to job updates stream"
        })

        # Keep connection alive and handle incoming messages
        while True:
            try:
                # Wait for any messages from client (ping/pong, etc.)
                # Timeout after 60 seconds to check connection health
                data = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=60.0
                )

                # Handle ping/pong for connection health
                if data == "ping":
                    await websocket.send_json({"type": "pong"})
                elif data == "pong":
                    pass  # Client acknowledged our ping

            except asyncio.TimeoutError:
                # No message received in 60s, connection might be dead
                # Try to send a ping to check
                try:
                    await websocket.send_json({"type": "ping"})
                except:
                    # Failed to send, connection is dead
                    break

            except WebSocketDisconnect:
                break
            except Exception as e:
                print(f"⚠️  WebSocket error: {e}")
                break

    finally:
        keepalive_task.cancel()
        manager.disconnect(websocket)


@router.on_event("startup")
async def startup_event():
    """Start background task for polling job updates."""
    asyncio.create_task(poll_job_updates())

