"""
Band Simulator — local offline MockBandRoom implementation.
Allows running SimpleAdapter agents in-process with event loop message routing.
"""

import asyncio
import uuid
from typing import Any

from band.core.simple_adapter import SimpleAdapter
from band.core.types import PlatformMessage, HistoryProvider, AgentInput
from band.testing.fake_tools import FakeAgentTools


class MockBandRoom:
    """A local in-memory event-driven Band Room simulator.

    Registers SimpleAdapters, routes messages via an asynchronous queue,
    and handles history reconstruction.
    """

    def __init__(self, room_id: str = "mock-room-123") -> None:
        self.room_id = room_id
        self.adapters: dict[str, SimpleAdapter] = {}
        self.messages: list[dict[str, Any]] = []
        self._queue: list[dict[str, Any]] = []
        self._processing = False

    def register_adapter(self, name: str, adapter: SimpleAdapter) -> None:
        """Register an adapter and set its agent name."""
        self.adapters[name] = adapter
        adapter.agent_name = name

    def add_message_synchronously(self, content: str, sender_name: str, sender_type: str = "agent") -> dict[str, Any]:
        """Adds a message to the room's message log immediately."""
        msg_id = f"msg-{len(self.messages)}"
        msg_dict = {
            "id": msg_id,
            "room_id": self.room_id,
            "content": content,
            "sender_id": f"id-{sender_name}",
            "sender_type": sender_type,
            "sender_name": sender_name,
            "message_type": "text",
            "metadata": {},
            "created_at": None,
        }
        self.messages.append(msg_dict)
        return msg_dict

    async def send_initial_message(self, content: str, sender_name: str = "Orchestrator") -> None:
        """Kicks off the evaluation by sending the initial trigger message."""
        msg_dict = self.add_message_synchronously(content, sender_name, "user")
        await self.enqueue_for_broadcast(msg_dict)

    async def enqueue_for_broadcast(self, msg_dict: dict[str, Any]) -> None:
        """Enqueues a message for broadcast."""
        self._queue.append(msg_dict)
        if not self._processing:
            await self._process_queue()

    async def _process_queue(self) -> None:
        self._processing = True
        try:
            while self._queue:
                msg_dict = self._queue.pop(0)
                sender_name = msg_dict["sender_name"]
                content = msg_dict["content"]

                # Nice visual output for the simulation
                print(f"📡 [Band Room] {sender_name}: {content}")

                # Deliver to all adapters except the sender
                tasks = []
                for name, adapter in self.adapters.items():
                    if name != sender_name:
                        tasks.append(self._deliver(name, adapter, msg_dict))
                if tasks:
                    await asyncio.gather(*tasks)
        finally:
            self._processing = False

    async def _deliver(self, name: str, adapter: SimpleAdapter, msg_dict: dict[str, Any]) -> None:
        # Create tools that route send_message back to MockBandRoom
        class RoutingTools(FakeAgentTools):
            def __init__(self, room: MockBandRoom, sender: str) -> None:
                super().__init__(room_id=room.room_id)
                self.room = room
                self.sender = sender

            async def send_message(self, content: str, mentions: Any = None) -> dict[str, Any]:
                # Add to messages synchronously so other agents in this tick see it in history
                msg_reply = self.room.add_message_synchronously(content, self.sender)
                # Non-blocking enqueue for delivery
                asyncio.create_task(self.room.enqueue_for_broadcast(msg_reply))
                return msg_reply

        tools = RoutingTools(self, name)

        # Build history containing previous messages (excluding the new one)
        history_msgs = [m for m in self.messages if m["id"] != msg_dict["id"]]

        msg = PlatformMessage(
            id=msg_dict["id"],
            room_id=msg_dict["room_id"],
            content=msg_dict["content"],
            sender_id=msg_dict["sender_id"],
            sender_type=msg_dict["sender_type"],
            sender_name=msg_dict["sender_name"],
            message_type=msg_dict["message_type"],
            metadata=msg_dict["metadata"],
            created_at=msg_dict["created_at"],
        )

        inp = AgentInput(
            msg=msg,
            tools=tools,
            history=HistoryProvider(raw=history_msgs),
            participants_msg=None,
            contacts_msg=None,
            is_session_bootstrap=(len(history_msgs) == 0),
            room_id=self.room_id,
        )

        try:
            # Let the adapter execute
            await adapter.on_event(inp)
        except Exception as e:
            print(f"❌ [Error] Agent '{name}' failed during execution: {e}")
            import traceback
            traceback.print_exc()
