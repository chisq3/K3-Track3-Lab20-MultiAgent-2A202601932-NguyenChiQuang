# Rubric Phản biện Chéo

Mỗi nhóm review repo/trace của một nhóm khác trong khoảng 8 phút.

| Tiêu chí | Câu hỏi đánh giá | Điểm |
|---|---|---:|
| Độ rõ vai trò | Mỗi agent có nhiệm vụ rõ ràng, không overlap quá mức không? | 0–2 |
| Thiết kế shared state | State có đủ thông tin cho handoff và debug mà không mất context không? | 0–2 |
| Guardrail lỗi | Có max iterations, timeout, retry/fallback và validation không? | 0–2 |
| Benchmark | Có so sánh single-agent và multi-agent bằng metric cụ thể không? | 0–2 |
| Giải thích trace | Nhóm giải thích được agent nào làm gì, tốn bao nhiêu và lỗi xảy ra ở đâu không? | 0–2 |

## Mẫu feedback

```text
Điểm mạnh:
Rủi ro / failure mode:
Một cải tiến cụ thể:
Điểm:
```

## Tự đánh giá bản triển khai này

Với final repo, các tiêu chí cốt lõi đều đã có evidence tương ứng: role separation, typed shared state, guardrail/retry/timeout, benchmark online + offline và LangSmith trace. Critic là phần bonus và được giữ bounded bằng `MAX_REVISIONS=1`.
