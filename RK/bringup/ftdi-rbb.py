"""Expose the board's FTDI A JTAG port as a local remote-bitbang cable."""
import argparse
import ctypes as c
import socket

parser = argparse.ArgumentParser()
parser.add_argument("--port", type=int, required=True)
parser.add_argument("--serial", required=True)
parser.add_argument("--gpio",type=lambda x:int(x,0), default=0x0008)
parser.add_argument("--direction",type=lambda x:int(x,0),default=0x001b)
opts = parser.parse_args()
ft = c.WinDLL("ftd2xx.dll")
handle = c.c_void_p()

def call(name, *args):
    rc = getattr(ft, name)(handle, *args)
    if rc:
        raise OSError(f"{name} returned {rc}")

def write(data):
    sent = c.c_ulong()
    call("FT_Write", bytes(data), c.c_ulong(len(data)), c.byref(sent))
    if sent.value != len(data):
        raise OSError(f"Short FTDI write: {sent.value}/{len(data)}")

def read(n):
    dest = c.create_string_buffer(n)
    got = c.c_ulong()
    call("FT_Read", dest, c.c_ulong(n), c.byref(got))
    if got.value != n:
        raise OSError(f"Short FTDI read: {got.value}/{n}")
    return dest.raw

rc = ft.FT_OpenEx(opts.serial.encode(), 1, c.byref(handle))
if rc:
    raise OSError(f"FT_OpenEx returned {rc}")
try:
    call("FT_SetUSBParameters", 65536, 65536)
    call("FT_SetTimeouts", 1500, 3000)
    call("FT_SetLatencyTimer", 1)
    call("FT_SetBitMode", 0, 0)
    call("FT_SetBitMode", opts.direction & 255, 2)
    import time
    time.sleep(0.03)
    call("FT_Purge", 3)
    write(bytes([0x80, opts.gpio & 255, opts.direction & 255, 0x82, opts.gpio >> 8, opts.direction >> 8, 0x8a, 0x97, 0x8d, 0x86, 0x3b, 0, 0xaa, 0x87]))
    if read(2) != b"\xfa\xaa":
        raise OSError("FTDI MPSSE sync failed")
    pin_data = [bytes((0x80, ((i & 4) >> 2) | ((i & 2) << 2) | ((i & 1) << 1) | (opts.gpio & 0xf0), opts.direction & 255)) for i in range(8)]
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", opts.port))
        listener.listen(1)
        print("FTDI remote-bitbang ready", flush=True)
        while True:
            conn, _ = listener.accept()
            with conn:
                conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                setting = False
                previous = 0
                for commands in iter(lambda: conn.recv(65536), b""):

                    output = bytearray()
                    samples = 0
                    clocks = 0
                    indices = []
                    finish = False
                    for cmd in commands:
                        if setting:
                            setting = False
                            continue
                        if cmd == 83:
                            setting = True
                            continue
                        if 48 <= cmd <= 55:
                            pins = cmd-48
                            if (pins & 4) and not (previous & 4):
                                output += bytes((0x6b, 0, ((pins & 2) >> 1) | ((pins & 1) << 7)))
                                clocks += 1
                            previous = pins
                        elif cmd == 82:  # R: sample TDO after preceding GPIO commands.
                            indices.append(clocks)
                            samples += 1
                        elif cmd == 81:  # Q
                            finish = True
                            break
                        elif cmd not in b"SBbtrsu":
                            raise ValueError(f"Unsupported remote-bitbang command {cmd:#x}")
                    if clocks:
                        output.append(0x87)
                    if output:
                        write(output)
                    captured = read(clocks) if clocks else b""
                    if samples:
                        response = bytes(49 if (captured[i] if i < len(captured) else 0) & 128 else 48 for i in indices)

                        conn.sendall(response)
                    if finish:
                        break
finally:
    call("FT_SetBitMode", 0, 0)
    call("FT_Close")
