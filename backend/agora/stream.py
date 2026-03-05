import json
import redis.asyncio as redis
from .models import AgoraMessage, MessageType

STREAM_KEY = "agora:log"
MAX_LEN = 5000


class AgoraStream:
    def __init__(self, r: redis.Redis):
        self.r = r

    async def publish(self, msg: AgoraMessage) -> str:
        data = {
            "epoch": str(msg.epoch),
            "agent_id": msg.agent_id,
            "type": msg.type.value,
            "payload": json.dumps(msg.payload, ensure_ascii=False),
            "ts": str(msg.ts),
        }
        msg_id = await self.r.xadd(STREAM_KEY, data, maxlen=MAX_LEN)
        return msg_id.decode()

    async def read_new(self, last_id: str = "$", timeout_ms: int = 200) -> list[tuple[str, AgoraMessage]]:
        """Block-read new messages. Returns list of (msg_id, message)."""
        entries = await self.r.xread({STREAM_KEY: last_id}, count=50, block=timeout_ms)
        result = []
        for _, msgs in entries:
            for msg_id, fields in msgs:
                mid = msg_id.decode()
                result.append((mid, self._decode(mid, fields)))
        return result

    async def get_all(self) -> list[AgoraMessage]:
        entries = await self.r.xrange(STREAM_KEY)
        return [self._decode(mid.decode(), fields) for mid, fields in entries]

    def _decode(self, msg_id: str, fields: dict) -> AgoraMessage:
        return AgoraMessage(
            id=msg_id,
            epoch=int(fields[b"epoch"]),
            agent_id=fields[b"agent_id"].decode(),
            type=MessageType(fields[b"type"].decode()),
            payload=json.loads(fields[b"payload"]),
            ts=float(fields[b"ts"]),
        )
