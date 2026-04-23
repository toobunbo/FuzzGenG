# Atheris `FuzzedDataProvider` — Reference

> Verified bằng thực nghiệm trên `atheris` Python 3.13, 2026-04-21.

---

## Khái niệm cốt lõi

`FuzzedDataProvider(data: bytes)` là một **stream reader** trên buffer bytes mà libFuzzer cung cấp.
Mỗi lần gọi một method sẽ **consume** một số bytes từ đầu buffer, theo thứ tự.
Khi hết bytes, các method trả về giá trị mặc định (0, `""`, `False`, …) thay vì raise exception.

```python
fdp = atheris.FuzzedDataProvider(data)
a = fdp.ConsumeInt(4)       # tiêu 4 bytes đầu
b = fdp.ConsumeBool()       # tiêu 1 byte tiếp theo
s = fdp.ConsumeString(20)   # tiêu 1 bytemark + tối đa 20 chars
```

**Thứ tự gọi quan trọng** — đổi thứ tự = bytes bị phân chia khác nhau = kết quả khác nhau.

Hai thuộc tính tiện dụng:
- `fdp.remaining_bytes()` — số bytes còn lại trong buffer.
- `fdp.buffer` — tham chiếu đến buffer gốc (ít dùng).

---

## 1. Boolean

### `ConsumeBool() → bool`
- Tiêu: **1 byte**
- Cơ chế: check **LSB** (bit thấp nhất), **không phải** zero/nonzero.

```python
# byte & 1 == 1 → True, byte & 1 == 0 → False
0x00 (0b00000000) → False
0x01 (0b00000001) → True
0x80 (0b10000000) → False   ← dễ nhầm! 128 là even number
0x81 (0b10000001) → True
0xff (0b11111111) → True
```

---

## 2. Integer

### `ConsumeInt(n: int) → int`
- Tiêu: **đúng `n` bytes**
- Cơ chế: little-endian **signed** integer.
- `n` tối đa: 9 bytes (72-bit integer).

```python
b'\x01'           → ConsumeInt(1) = 1
b'\x81'           → ConsumeInt(1) = -127      # 0x81 - 0x100
b'\x01\x02'       → ConsumeInt(2) = 513       # 0x0201 little-endian
b'\x01\x02\x03\x04' → ConsumeInt(4) = 67305985  # 0x04030201
b'\xff\xff\xff\xff'  → ConsumeInt(4) = -1
```

### `ConsumeUInt(n: int) → int`
- Tiêu: **đúng `n` bytes**
- Cơ chế: little-endian **unsigned** integer (giống `ConsumeInt` nhưng không có phần âm).

```python
b'\x81'           → ConsumeUInt(1) = 129      # không âm
b'\xff\xff\xff\xff' → ConsumeUInt(4) = 4294967295
```

### `ConsumeIntInRange(min: int, max: int) → int`
- Tiêu: **tối thiểu số bytes đủ để biểu diễn `max - min + 1` giá trị**

| Kích thước range | Bytes tiêu |
|---|---|
| ≤ 256 (fits 1 byte) | 1 |
| ≤ 65,536 | 2 |
| ≤ 2³² | 4 |
| ≤ 2⁶⁴ | 8 |
| ≤ 2⁷² | 9 |

```python
# bytes \x00...  → min, bytes \xff... → max (xấp xỉ)
b'\x00'*9 → ConsumeIntInRange(0, 100) = 0
b'\xff'*9 → ConsumeIntInRange(0, 100) = 53   # map đều, không nhất thiết = max
```

### `ConsumeIntList(count: int, n_bytes: int) → List[int]`
- Tiêu: **`count × n_bytes`** bytes
- Trả về list `count` signed integers, mỗi cái `n_bytes` bytes (little-endian).

```python
b'\x00\x01\x02\x03' → ConsumeIntList(4, 1) = [0, 1, 2, 3]
b'\x01\x02\x03\x04\x05\x06' → ConsumeIntList(3, 2) = [513, 1027, 1541]
#  ↑ [0x0201, 0x0403, 0x0605]
```

### `ConsumeIntListInRange(count: int, min: int, max: int) → List[int]`
- Tiêu: `count` lần × bytes-per-IntInRange(min, max)
- Trả về list `count` integers, mỗi cái trong `[min, max]`.

```python
b'\x00'*100 → ConsumeIntListInRange(4, 0, 10) = [0, 0, 0, 0]
b'\xff'*100 → ConsumeIntListInRange(4, 0, 10) = [2, 2, 2, 2]
```

---

## 3. Float

### `ConsumeFloat() → float`
- Tiêu: **10 bytes**
- **Byte đầu tiên** quyết định loại giá trị đặc biệt:

| Byte đầu | Kết quả |
|---|---|
| `0x00` | `+0.0` |
| `0x01` | `-0.0` |
| `0x02` | `+inf` |
| `0x03` | `-inf` |
| `0x04` | `NaN` |
| `0x05` | nhỏ nhất dương (denormalized) |
| `0x06` | nhỏ nhất âm (denormalized) |
| `0x07` | nhỏ nhất dương (normalized) |
| `0x08` | nhỏ nhất âm (normalized) |
| `0x09` | lớn nhất dương (`1.797e+308`) |
| `0x0a` | lớn nhất âm (`-1.797e+308`) |
| `>= 0x0b` | float ngẫu nhiên (có thể inf/nan) |

### `ConsumeRegularFloat() → float`
- Tiêu: **9 bytes**
- Giống `ConsumeFloat` nhưng **đảm bảo không trả về** `inf` hoặc `NaN`.
- Range: `[-1.797e+308, +1.797e+308]`.

```python
b'\x00'*9 → -1.797e+308
b'\xff'*9 → +1.797e+308
```

### `ConsumeFloatInRange(min: float, max: float) → float`
- Tiêu: **10 bytes**
- Map đều vào `[min, max]`.

```python
b'\x00'*10 → ConsumeFloatInRange(0.0, 1.0) = 0.0
b'\xff'*10 → ConsumeFloatInRange(0.0, 1.0) = 1.0
```

### `ConsumeProbability() → float`
- Tiêu: **8 bytes**
- Luôn trả về float trong `[0.0, 1.0]` — shorthand cho `ConsumeFloatInRange(0.0, 1.0)` với 8 bytes.

```python
b'\x00'*8 → 0.0
b'\x80'*8 → ~0.502
b'\xff'*8 → 1.0
```

### `ConsumeFloatList(count: int) → List[float]`
- Tiêu: `count × 10 bytes`
- Trả về list `count` floats (có thể chứa inf/nan).

### `ConsumeRegularFloatList(count: int) → List[float]`
- Tiêu: `count × 9 bytes`
- Trả về list `count` floats, **không có** inf/nan.

### `ConsumeFloatListInRange(count: int, min: float, max: float) → List[float]`
- Tiêu: `count × 10 bytes`
- Trả về list `count` floats trong `[min, max]`.

### `ConsumeProbabilityList(count: int) → List[float]`
- Tiêu: `count × 8 bytes`
- Trả về list `count` floats trong `[0.0, 1.0]`.

---

## 4. Bytes & String

### `ConsumeBytes(n: int) → bytes`
- Tiêu: **đúng `n` bytes**
- Trả về raw bytes, **không transform gì**. Đây là method "trung thực" nhất.

```python
b'hello_world' → ConsumeBytes(5) = b'hello', ConsumeBytes(6) = b'_world'
```

### `ConsumeString(max_len: int) → str`
- Tiêu: **1 byte bytemark** + payload (tùy mode và `max_len`)
- **Byte đầu tiên** quyết định encoding mode:

| Bytemark | Mode | Bytes/char | Ghi chú |
|---|---|---|---|
| `\x00` | UTF-32 | 4 | 4 bytes → 1 code point (little-endian) |
| `\x01` | ASCII | 1 | 1 byte → 1 char (latin-1, 0–255) |
| `\x02` | UTF-16 | 2 | 2 bytes → 1 char (little-endian) |
| khác | fallback | ≥3 | merge nhiều bytes → code point cao (U+10xxxx) |

```python
b'\x01' + b'http://127.0.0.1' → ConsumeString(20) = 'http://127.0.0.1'  ✅
b'http://127.0.0.1'            → ConsumeString(20) = '\U00107474...'     ❌ garbage
```

> **Quan trọng với seed corpus:** Seeds lưu dạng raw UTF-8 string sẽ bị hỏng khi qua `ConsumeString`.
> Phải prefix `\x01` để ép ASCII mode:
> ```python
> f.write(b'\x01' + seed.encode('utf-8'))
> ```
> Hoặc dùng `data.decode('utf-8', errors='replace')` trực tiếp thay vì `ConsumeString`.

### `ConsumeUnicode(max_len: int) → str`
- Cơ chế giống hệt `ConsumeString` (thực ra cùng implementation).
- Có thể trả về surrogate code points (U+D800–U+DFFF).

### `ConsumeUnicodeNoSurrogates(max_len: int) → str`
- Giống `ConsumeUnicode` nhưng thay thế surrogate bằng cách trừ 0xD800.
- An toàn hơn khi cần string valid Unicode hoàn toàn.

---

## 5. Chọn từ tập hợp

### `PickValueInList(lst: list) → Any`
- Tiêu: bytes tối thiểu đủ để index vào `lst`

| `len(lst)` | Bytes tiêu |
|---|---|
| ≤ 256 | 1 |
| ≤ 1000 | 2 |
| ≤ 65,536 | 2 |

```python
lst = ['alpha', 'beta', 'gamma', 'delta']
b'\x00'*2 → 'alpha'
b'\x01'*2 → 'beta'
b'\xff'*2 → 'delta'
```

---

## 6. Hằng số

### `atheris.ALL_REMAINING`
Dùng làm `max_len` để consume **tất cả bytes còn lại** trong một lần gọi.

```python
image_file = fdp.ConsumeString(atheris.ALL_REMAINING)
```

---

## Bảng tổng hợp nhanh

| Method | Bytes tiêu | Output type | Ghi chú |
|---|---|---|---|
| `ConsumeBool()` | 1 | `bool` | check LSB, không phải zero/nonzero |
| `ConsumeInt(n)` | n | `int` | little-endian signed |
| `ConsumeUInt(n)` | n | `int` | little-endian unsigned |
| `ConsumeIntInRange(lo, hi)` | min bytes cho range | `int` | 1–9 bytes tùy range size |
| `ConsumeIntList(count, n)` | count×n | `List[int]` | |
| `ConsumeIntListInRange(count, lo, hi)` | count × (min bytes cho range) | `List[int]` | |
| `ConsumeFloat()` | 10 | `float` | có thể inf/nan; byte[0] chọn special case |
| `ConsumeRegularFloat()` | 9 | `float` | không bao giờ inf/nan |
| `ConsumeFloatInRange(lo, hi)` | 10 | `float` | |
| `ConsumeProbability()` | 8 | `float` | luôn trong [0.0, 1.0] |
| `ConsumeFloatList(count)` | count×10 | `List[float]` | có thể inf/nan |
| `ConsumeRegularFloatList(count)` | count×9 | `List[float]` | không inf/nan |
| `ConsumeFloatListInRange(count, lo, hi)` | count×10 | `List[float]` | |
| `ConsumeProbabilityList(count)` | count×8 | `List[float]` | [0.0, 1.0] |
| `ConsumeBytes(n)` | n | `bytes` | raw, không transform |
| `ConsumeString(max_len)` | 1 + payload | `str` | byte[0] là bytemark encoding |
| `ConsumeUnicode(max_len)` | 1 + payload | `str` | giống ConsumeString |
| `ConsumeUnicodeNoSurrogates(max_len)` | 1 + payload | `str` | không có surrogate pairs |
| `PickValueInList(lst)` | 1–2 | `Any` | tùy len(lst) |

---

## Pattern dùng trong harness thực tế

```python
def TestOneInput(data):
    fdp = atheris.FuzzedDataProvider(data)

    # --- Cách 1: dùng ConsumeString đúng cách ---
    url = fdp.ConsumeString(200)           # cần seed prefix \x01
    # hoặc
    url = data.decode('utf-8', errors='replace')  # đơn giản hơn, không cần bytemark

    # --- Cách 2: nhiều params ---
    method  = fdp.PickValueInList(['GET', 'POST', 'PUT', 'DELETE'])
    timeout = fdp.ConsumeIntInRange(0, 30)
    verify  = fdp.ConsumeBool()
    body    = fdp.ConsumeBytes(fdp.remaining_bytes())   # lấy hết phần còn lại

    # --- Seed corpus đúng cách cho ConsumeString ---
    # f.write(b'\x01' + seed.encode('utf-8'))
```
