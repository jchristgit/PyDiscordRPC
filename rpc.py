import asyncio
import json
import os
import struct
import subprocess
import sys
import time
import uuid


def script(action):
    r = subprocess.run(["osascript", "-e", f"tell app \"music\" to {action}"], stdout=subprocess.PIPE)
    return r.stdout.decode('utf-8')


class DiscordRPC:
    def __init__(self):
        if sys.platform == 'linux' or sys.platform == 'darwin':
            env_vars = ['XDG_RUNTIME_DIR', 'TMPDIR', 'TMP', 'TEMP']
            path = next((os.environ.get(path, None) for path in env_vars if path in os.environ), '/tmp')
            self.ipc_path = f'{path}/discord-ipc-0'
            self.loop = asyncio.get_event_loop()
        elif sys.platform == 'win32':
            self.ipc_path = r'\\?\pipe\discord-ipc-0'
            self.loop = asyncio.ProactorEventLoop()

        self.sock_reader: asyncio.StreamReader = None
        self.sock_writer: asyncio.StreamWriter = None

    async def read_output(self):
        while True:
            data = await self.sock_reader.read(1024)
            if data == b'':
                self.sock_writer.close()
                exit(0)
            try:
                code, length = struct.unpack('<ii', data[:8])
                print(f'OP Code: {code}; Length: {length}\nResponse:\n{json.loads(data[8:].decode("utf-8"))}\n')
            except struct.error:
                print(f'Something happened\n{data}')

    def send_data(self, op: int, payload: dict):
        payload = json.dumps(payload)
        self.sock_writer.write(struct.pack('<ii', op, len(payload)) + payload.encode('utf-8'))

    async def handshake(self):
        if sys.platform == 'linux' or sys.platform == 'darwin':
            self.sock_reader, self.sock_writer = await asyncio.open_unix_connection(self.ipc_path)
        elif sys.platform == 'win32':
            self.sock_reader = asyncio.StreamReader()
            reader_protocol = asyncio.StreamReaderProtocol(self.sock_reader)
            self.sock_writer, _ = await self.loop.create_pipe_connection(lambda: reader_protocol, self.ipc_path)

        self.send_data(0, {'v': 1, 'client_id': '409024517617221643'})
        data = await self.sock_reader.read(1024)
        code, length = struct.unpack('<ii', data[:8])
        print(f'OP Code: {code}; Length: {length}\nResponse:\n{json.loads(data[8:].decode("utf-8"))}\n')

    def send_rich_presence(self):
        current_time = int(time.time())
        duration = script("duration of current track")
        player_pos = script("player position")
        track_name = script("return name of current track")
        artist = script("return artist of current track")
        playing = script("return player state is playing") == 'true\n'
        left = current_time + (int(duration.split('.')[0]) - int(player_pos.split('.')[0]))
        payload = {
            'cmd': 'SET_ACTIVITY',
            'args': {
                'activity': {
                    'state': artist if playing else 'Paused',
                    'details': track_name,
                    'assets': {
                        'large_text': 'iTunes',
                        'large_image': 'itunes'
                    },
                    'instance': True
                },
                'pid': os.getpid()
            },
            'nonce': str(uuid.uuid4())
        }
        if playing:
            payload['args']['activity']['timestamps'] = {
                'end': left
            }
        self.send_data(1, payload)

    async def run(self):
        await self.handshake()
        while True:
            try:
                self.send_rich_presence()
                await asyncio.sleep(10)
            except KeyboardInterrupt:
                break
        self.close()
        # await self.read_output()

    def close(self):
        self.sock_writer.close()
        self.loop.close()
        exit(0)


if __name__ == '__main__':
    rpc = DiscordRPC()
    try:
        rpc.loop.run_until_complete(rpc.run())
    except KeyboardInterrupt:
        rpc.close()
