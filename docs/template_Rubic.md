# Fuzzing Harness Evaluation Rubric
> Atheris / Python — v2

---

## Findings

```

```

---

## Harness

```
(để trống — tên file / link hoặc paste harness vào đây)
```

---

## Evaluation

### C1 — Input Generation

> FDP type có khớp với signature hàm mục tiêu không? Đủ tham số bắt buộc?

Notes:

---

### C2 — Mock / Patch Setup

> Patch đúng target? Mock đủ attributes? Scope đúng (context manager)?
> *(Bỏ qua nếu harness không dùng mock)*
Notes:

---

### C3 — Function Call Correctness

> Đúng tên hàm, đúng số lượng + thứ tự tham số, đúng kiểu?
Notes:

---

### C4 — Oracle Design

> Oracle đặt đúng vị trí (ngoài try/except)? Logic detect đúng vuln class? Raise signal rõ ràng?

Notes:

---

### C5 — Exception Handling

> Re-raise đúng signal exception? Swallow có chủ đích các exception nhiễu từ target?

Notes:

---

## Researcher Notes

**Edge cases chưa cover:**

**Đề xuất cải thiện:**

