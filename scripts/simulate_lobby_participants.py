"""Keep multiple real HTTP participant sessions online for lobby motion testing."""

import argparse
import json
import time
from http.client import RemoteDisconnected
from http.cookiejar import CookieJar
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPCookieProcessor, Request, build_opener


class ParticipantSession:
    def __init__(self, base_url: str, code: str, name: str):
        self.base_url = base_url.rstrip("/")
        self.code = code
        self.name = name
        self.opener = build_opener(HTTPCookieProcessor(CookieJar()))

    def post_form(self, path: str, payload: dict | None = None):
        body = urlencode(payload or {}).encode("utf-8")
        request = Request(f"{self.base_url}{path}", data=body, method="POST")
        return self.opener.open(request, timeout=10)

    def join(self):
        response = self.post_form("/join", {"name": self.name, "code": self.code})
        return response.status, response.geturl()

    def heartbeat(self):
        return self.post_form("/api/presence/heartbeat").status

    def boost(self):
        return self.post_form("/api/lobby/boost").read().decode("utf-8")

    def leave(self):
        return self.post_form("/leave").status


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("code")
    parser.add_argument("--base-url", default="http://localhost:5000")
    parser.add_argument("--count", type=int, default=12)
    parser.add_argument("--duration", type=int, default=1800)
    parser.add_argument("--boost-every", type=int, default=0, help="Activate the first participant's boost every N seconds")
    args = parser.parse_args()

    participants = []
    for index in range(1, args.count + 1):
        participant = ParticipantSession(args.base_url, args.code.upper(), f"DVD Test {index:02d}")
        try:
            status, location = participant.join()
            participants.append(participant)
            print(json.dumps({"event": "joined", "name": participant.name, "status": status, "location": location}), flush=True)
        except (HTTPError, URLError, RemoteDisconnected, TimeoutError, OSError) as error:
            print(json.dumps({"event": "join_failed", "name": participant.name, "error": str(error)}), flush=True)

    started_at = time.monotonic()
    last_boost_at = 0.0
    try:
        while participants and time.monotonic() - started_at < args.duration:
            now = time.monotonic()
            if args.boost_every > 0 and now - last_boost_at >= args.boost_every:
                try:
                    print(json.dumps({"event": "boost", "response": json.loads(participants[0].boost())}), flush=True)
                    last_boost_at = now
                except (HTTPError, URLError, RemoteDisconnected, TimeoutError, OSError) as error:
                    print(json.dumps({"event": "boost_failed", "error": str(error)}), flush=True)

            time.sleep(20)
            online = 0
            for participant in participants:
                try:
                    if participant.heartbeat() == 200:
                        online += 1
                except (HTTPError, URLError, RemoteDisconnected, TimeoutError, OSError) as error:
                    print(json.dumps({"event": "heartbeat_failed", "name": participant.name, "error": str(error)}), flush=True)
            print(json.dumps({"event": "heartbeat", "online": online, "sessions": len(participants)}), flush=True)
    finally:
        for participant in participants:
            try:
                participant.leave()
            except (HTTPError, URLError, RemoteDisconnected, TimeoutError, OSError):
                pass


if __name__ == "__main__":
    main()
