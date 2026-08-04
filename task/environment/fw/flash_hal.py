"""In-memory NOR flash HAL."""

PAGE_SIZE = 256
NUM_PAGES = 32
JOURNAL_PAGES = 28  # pages 0..27
SLOT_A_PAGE = 28
SLOT_B_PAGE = 29
META_PAGE = 30
META_MIRROR_PAGE = 31


class Flash:
    def __init__(self):
        self.mem = bytearray([0xFF] * (PAGE_SIZE * NUM_PAGES))

    def read(self, addr: int, n: int) -> bytes:
        return bytes(self.mem[addr : addr + n])

    def program(self, addr: int, data: bytes) -> None:
        # Host simulation allows byte rewrite so two-phase header seals can set SEAL_PAY.
        self.mem[addr : addr + len(data)] = data

    def erase_page(self, page: int) -> None:
        base = page * PAGE_SIZE
        self.mem[base : base + PAGE_SIZE] = b"\xff" * PAGE_SIZE

    def page_bytes(self, page: int) -> bytearray:
        base = page * PAGE_SIZE
        return self.mem[base : base + PAGE_SIZE]
