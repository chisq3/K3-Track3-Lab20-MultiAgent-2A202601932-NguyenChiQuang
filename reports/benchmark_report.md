# Báo cáo Benchmark Online

Ngày tạo benchmark: 2026-08-20

## Thiết lập Thí nghiệm

- Model: `openai/gpt-4o-mini`.
- LLM endpoint: `https://openrouter.ai/api/v1`.
- Search provider: Tavily thông qua `SearchClient` của repo.
- Temperature: baseline 0.2; Researcher 0.2; Analyst 0.1; Writer 0.4; Critic 0.0; blind quality judge 0.0.
- Cost ưu tiên provider-reported usage từ OpenRouter; nếu provider cost không đầy đủ thì ghi `n/a`, không tự áp giá của provider khác.

### Bộ test

| Case | Query | Đối tượng | Số nguồn tối đa |
|---|---|---|---:|
| graphrag | Research GraphRAG state-of-the-art and write a 500-word summary | technical learners | 5 |
| customer-support | Compare single-agent and multi-agent workflows for customer support | technical learners | 5 |
| production-guardrails | Summarize production guardrails for LLM agents | technical learners | 5 |

## Phương pháp

- So sánh `baseline`, `multi-agent` và `multi-agent-critic` trên cùng bộ case.
- Thứ tự variant được xoay giữa các repeat để giảm bias latency do thứ tự chạy.
- Quality được chấm bằng cùng một blind LLM judge 0–10 cho mọi kiến trúc.
- Citation coverage là proxy deterministic ở mức câu: số câu nội dung có inline citation `[n]` chia cho tổng số câu nội dung.
- Citation validity dùng tiêu chí strict: citation ID và source URL cuối phải khớp source set đã cung cấp.
- Cost/tokens của kiến trúc không tính independent quality-judge call; usage của judge được lưu riêng trong raw results.
- Một run chỉ được tính thành công khi final status là `completed`; `partial` được tính vào failure rate.

## Kết quả Tổng hợp

| Kiến trúc | Runs | Thành công | Latency (s) | Tokens | Cost (USD) | Quality /10 | Citation coverage | Citation validity | Iterations | Revisions |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| baseline | 9 | 100% | 17.35 | 2205 | 0.000651 | 10.00 | 40% | 67% | 1.0 | 0.00 |
| multi-agent | 9 | 78% | 43.09 | 9028 | 0.002083 | 9.86 | 33% | 100% | 4.2 | 0.00 |
| multi-agent-critic | 9 | 56% | 45.49 | 14085 | 0.002873 | 10.00 | 33% | 100% | 5.7 | 0.11 |

## Trade-off Quan sát được

- Multi-agent so với baseline: latency +148.3%, tokens +309.5%, quality -0.14 points, citation coverage -7.2 điểm phần trăm.
- Critic so với core multi-agent: latency +5.6%, tokens +56.0%, quality +0.14 points, citation coverage -0.4 điểm phần trăm.

## Kết quả Từng Run

| Kiến trúc | Query | Repeat | Trạng thái | Latency (s) | Tokens | Cost | Quality | Citation coverage | Hợp lệ | Retries | Revisions | Lý do dừng | Trace |
|---|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| baseline | graphrag | 1 | completed | 13.10 | 2062 | 0.000658 | 10.00 | 40% | 100% | 0 | 0 | completed | 01a01f07-ecb1-76e1-8dc3-4d87dd2ab1fe |
| multi-agent | graphrag | 1 | completed | 28.64 | 7641 | 0.002040 | 9.00 | 39% | 100% | 0 | 0 | completed | [trace](https://smith.langchain.com/o/0e2fbfaf-b11b-43a8-a13d-dd195ec58964/projects/p/a205b094-b4a3-4f15-a5c0-528321a0e6d4/r/01a01f08-a1ef-7051-a18b-15df403032c9?poll=true) |
| multi-agent-critic | graphrag | 1 | failed | 40.76 | 10980 | 0.002636 | n/a | n/a | n/a | 1 | 0 | writer_failed | [trace](https://smith.langchain.com/o/0e2fbfaf-b11b-43a8-a13d-dd195ec58964/projects/p/a205b094-b4a3-4f15-a5c0-528321a0e6d4/r/01a01f09-1a91-73d3-a26f-0c9995f6d717?poll=true) |
| baseline | customer-support | 1 | completed | 45.89 | 2334 | 0.000726 | 10.00 | 39% | 100% | 0 | 0 | completed | [trace](https://smith.langchain.com/o/0e2fbfaf-b11b-43a8-a13d-dd195ec58964/projects/p/a205b094-b4a3-4f15-a5c0-528321a0e6d4/r/01a01f09-b9ce-7d00-b246-e092d5675f27?poll=true) |
| multi-agent | customer-support | 1 | failed | 66.23 | 2028 | 0.000558 | n/a | n/a | n/a | 0 | 0 | timeout | [trace](https://smith.langchain.com/o/0e2fbfaf-b11b-43a8-a13d-dd195ec58964/projects/p/a205b094-b4a3-4f15-a5c0-528321a0e6d4/r/01a01f0a-7aa1-76e3-901b-ac406d6cb8cd?poll=true) |
| multi-agent-critic | customer-support | 1 | failed | 45.75 | 11723 | 0.002760 | n/a | n/a | n/a | 1 | 0 | writer_failed | [trace](https://smith.langchain.com/o/0e2fbfaf-b11b-43a8-a13d-dd195ec58964/projects/p/a205b094-b4a3-4f15-a5c0-528321a0e6d4/r/01a01f0b-7d54-7b11-b1ed-d4ab4f762317?poll=true) |
| baseline | production-guardrails | 1 | completed | 15.01 | 2244 | 0.000690 | 10.00 | 45% | 100% | 0 | 0 | completed | [trace](https://smith.langchain.com/o/0e2fbfaf-b11b-43a8-a13d-dd195ec58964/projects/p/a205b094-b4a3-4f15-a5c0-528321a0e6d4/r/01a01f0c-3006-78a1-b65c-601b10a03790?poll=true) |
| multi-agent | production-guardrails | 1 | completed | 35.15 | 8415 | 0.002227 | 10.00 | 27% | 100% | 0 | 0 | completed | [trace](https://smith.langchain.com/o/0e2fbfaf-b11b-43a8-a13d-dd195ec58964/projects/p/a205b094-b4a3-4f15-a5c0-528321a0e6d4/r/01a01f0c-74bd-7090-b0e8-46073d1e090b?poll=true) |
| multi-agent-critic | production-guardrails | 1 | completed | 35.83 | 11992 | 0.002557 | 10.00 | 37% | 100% | 0 | 0 | completed | [trace](https://smith.langchain.com/o/0e2fbfaf-b11b-43a8-a13d-dd195ec58964/projects/p/a205b094-b4a3-4f15-a5c0-528321a0e6d4/r/01a01f0d-07ca-7c11-bb6d-4d40a84be31f?poll=true) |
| multi-agent | graphrag | 2 | failed | 66.09 | 11168 | 0.002478 | n/a | n/a | n/a | 1 | 0 | timeout | [trace](https://smith.langchain.com/o/0e2fbfaf-b11b-43a8-a13d-dd195ec58964/projects/p/a205b094-b4a3-4f15-a5c0-528321a0e6d4/r/01a01f0d-a2f1-7ea1-bd15-ad653123d7ab?poll=true) |
| multi-agent-critic | graphrag | 2 | failed | 50.34 | 11193 | 0.002508 | n/a | n/a | n/a | 1 | 0 | writer_failed | [trace](https://smith.langchain.com/o/0e2fbfaf-b11b-43a8-a13d-dd195ec58964/projects/p/a205b094-b4a3-4f15-a5c0-528321a0e6d4/r/01a01f0e-a517-79d2-bd12-49b4770773fa?poll=true) |
| baseline | graphrag | 2 | completed | 10.80 | 2051 | 0.000651 | 10.00 | 37% | 0% | 0 | 0 | completed | [trace](https://smith.langchain.com/o/0e2fbfaf-b11b-43a8-a13d-dd195ec58964/projects/p/a205b094-b4a3-4f15-a5c0-528321a0e6d4/r/01a01f0f-69bc-76b2-a3c4-f69f22d052a4?poll=true) |
| multi-agent | customer-support | 2 | completed | 38.94 | 8744 | 0.002120 | 10.00 | 41% | 100% | 0 | 0 | completed | [trace](https://smith.langchain.com/o/0e2fbfaf-b11b-43a8-a13d-dd195ec58964/projects/p/a205b094-b4a3-4f15-a5c0-528321a0e6d4/r/01a01f0f-9d98-7c92-b7ff-aa73ceac8aa0?poll=true) |
| multi-agent-critic | customer-support | 2 | completed | 51.16 | 15273 | 0.003021 | 10.00 | 29% | 100% | 1 | 0 | completed | [trace](https://smith.langchain.com/o/0e2fbfaf-b11b-43a8-a13d-dd195ec58964/projects/p/a205b094-b4a3-4f15-a5c0-528321a0e6d4/r/01a01f10-41c9-7000-b891-6ac6333840c9?poll=true) |
| baseline | customer-support | 2 | completed | 15.30 | 2424 | 0.000780 | 10.00 | 41% | 100% | 0 | 0 | completed | [trace](https://smith.langchain.com/o/0e2fbfaf-b11b-43a8-a13d-dd195ec58964/projects/p/a205b094-b4a3-4f15-a5c0-528321a0e6d4/r/01a01f11-1dcc-7f43-9ce9-3eea736fba63?poll=true) |
| multi-agent | production-guardrails | 2 | completed | 42.76 | 12185 | 0.002625 | 10.00 | 35% | 100% | 1 | 0 | completed | [trace](https://smith.langchain.com/o/0e2fbfaf-b11b-43a8-a13d-dd195ec58964/projects/p/a205b094-b4a3-4f15-a5c0-528321a0e6d4/r/01a01f11-69a6-7600-af00-2d947a53e3bc?poll=true) |
| multi-agent-critic | production-guardrails | 2 | completed | 45.55 | 15016 | 0.002934 | 10.00 | 38% | 100% | 1 | 0 | completed | [trace](https://smith.langchain.com/o/0e2fbfaf-b11b-43a8-a13d-dd195ec58964/projects/p/a205b094-b4a3-4f15-a5c0-528321a0e6d4/r/01a01f12-18fa-7b31-9855-b88e7521af68?poll=true) |
| baseline | production-guardrails | 2 | completed | 15.01 | 2161 | 0.000534 | 10.00 | 35% | 100% | 0 | 0 | completed | [trace](https://smith.langchain.com/o/0e2fbfaf-b11b-43a8-a13d-dd195ec58964/projects/p/a205b094-b4a3-4f15-a5c0-528321a0e6d4/r/01a01f12-d3e7-7012-9e36-f0d78d38e88c?poll=true) |
| multi-agent-critic | graphrag | 3 | partial | 60.74 | 22630 | 0.003908 | 10.00 | 27% | 100% | 1 | 1 | critic_failed | [trace](https://smith.langchain.com/o/0e2fbfaf-b11b-43a8-a13d-dd195ec58964/projects/p/a205b094-b4a3-4f15-a5c0-528321a0e6d4/r/01a01f13-245a-7481-8d5f-8c63d4bcc3e5?poll=true) |
| baseline | graphrag | 3 | completed | 13.40 | 2068 | 0.000662 | 10.00 | 44% | 0% | 0 | 0 | completed | [trace](https://smith.langchain.com/o/0e2fbfaf-b11b-43a8-a13d-dd195ec58964/projects/p/a205b094-b4a3-4f15-a5c0-528321a0e6d4/r/01a01f14-1e24-7ae2-a1b7-27f6e182c887?poll=true) |
| multi-agent | graphrag | 3 | completed | 31.74 | 7752 | 0.001839 | 10.00 | 30% | 100% | 0 | 0 | completed | [trace](https://smith.langchain.com/o/0e2fbfaf-b11b-43a8-a13d-dd195ec58964/projects/p/a205b094-b4a3-4f15-a5c0-528321a0e6d4/r/01a01f14-5a00-7010-ba6e-99e3a5552e40?poll=true) |
| multi-agent-critic | customer-support | 3 | completed | 47.12 | 15850 | 0.003118 | 10.00 | 30% | 100% | 1 | 0 | completed | [trace](https://smith.langchain.com/o/0e2fbfaf-b11b-43a8-a13d-dd195ec58964/projects/p/a205b094-b4a3-4f15-a5c0-528321a0e6d4/r/01a01f14-dd18-7ac1-a8a6-887d5c44d099?poll=true) |
| baseline | customer-support | 3 | completed | 14.78 | 2284 | 0.000591 | 10.00 | 33% | 100% | 0 | 0 | completed | [trace](https://smith.langchain.com/o/0e2fbfaf-b11b-43a8-a13d-dd195ec58964/projects/p/a205b094-b4a3-4f15-a5c0-528321a0e6d4/r/01a01f15-a223-7382-8da9-548c3b9de239?poll=true) |
| multi-agent | customer-support | 3 | completed | 41.11 | 11467 | 0.002381 | 10.00 | 29% | 100% | 1 | 0 | completed | [trace](https://smith.langchain.com/o/0e2fbfaf-b11b-43a8-a13d-dd195ec58964/projects/p/a205b094-b4a3-4f15-a5c0-528321a0e6d4/r/01a01f15-e93f-7c02-8f40-e8f8def57e65?poll=true) |
| multi-agent-critic | production-guardrails | 3 | completed | 32.17 | 12107 | 0.002415 | 10.00 | 35% | 100% | 0 | 0 | completed | [trace](https://smith.langchain.com/o/0e2fbfaf-b11b-43a8-a13d-dd195ec58964/projects/p/a205b094-b4a3-4f15-a5c0-528321a0e6d4/r/01a01f16-9725-7da0-9cab-b45c7146b135?poll=true) |
| baseline | production-guardrails | 3 | completed | 12.86 | 2217 | 0.000568 | 10.00 | 48% | 0% | 0 | 0 | completed | [trace](https://smith.langchain.com/o/0e2fbfaf-b11b-43a8-a13d-dd195ec58964/projects/p/a205b094-b4a3-4f15-a5c0-528321a0e6d4/r/01a01f17-1d8d-7a70-91b3-d2255c7ff5f4?poll=true) |
| multi-agent | production-guardrails | 3 | completed | 37.14 | 11856 | 0.002477 | 10.00 | 30% | 100% | 1 | 0 | completed | [trace](https://smith.langchain.com/o/0e2fbfaf-b11b-43a8-a13d-dd195ec58964/projects/p/a205b094-b4a3-4f15-a5c0-528321a0e6d4/r/01a01f17-57b8-7c60-8a7a-695b31abfa7f?poll=true) |

## Phân tích Failure

| Kiến trúc | Query | Repeat | Trạng thái | Lý do dừng | Ghi chú |
|---|---|---:|---|---|---|
| multi-agent-critic | graphrag | 1 | failed | writer_failed | Phần Sources chứa URL của nguồn không được trích dẫn; Phần Sources thiếu citation label cho source ID: [1, 2, 3, 4] |
| multi-agent | customer-support | 1 | failed | timeout |  |
| multi-agent-critic | customer-support | 1 | failed | writer_failed | Phần Sources thiếu citation label cho source ID: [1, 2, 3, 4, 5]; Phần Sources thiếu citation label cho source ID: [1, 2, 3, 4, 5] |
| multi-agent | graphrag | 2 | failed | timeout | Phần Sources chứa URL của nguồn không được trích dẫn; Phần Sources thiếu citation label cho source ID: [1, 2, 3, 4, 5] |
| multi-agent-critic | graphrag | 2 | failed | writer_failed | Phần Sources thiếu citation label cho source ID: [1, 2, 3, 4, 5]; Phần Sources chứa URL của nguồn không được trích dẫn |
| multi-agent-critic | graphrag | 3 | partial | critic_failed | Quyết định `revise` của Critic phải kèm ít nhất một vấn đề cần sửa; Quyết định `revise` của Critic phải kèm ít nhất một vấn đề cần sửa |

## Ghi chú Diễn giải

Không giả định multi-agent luôn tốt hơn. Kiến trúc đắt hơn chỉ hợp lý khi lợi ích về grounding, citation, auditability hoặc failure handling đủ quan trọng với bài toán mục tiêu.

Kết quả Critic trong workflow chỉ mang tính diagnostic. Cột quality aggregate dùng independent blind judge, vì vậy Critic không tự chấm điểm cho chính variant của mình.

## Diễn giải End-to-End

Một metric tổng hợp hữu ích là **valid completed rate**: tỷ lệ run vừa `completed` vừa đạt strict `citation_validity == 1`.

| Kiến trúc | Valid completed online |
|---|---:|
| Baseline | 6/9 = 66.7% |
| Multi-agent core | **7/9 = 77.8%** |
| Multi-agent + Critic | 5/9 = 55.6% |

Core multi-agent có valid-completed rate cao nhất trong benchmark online, nhưng đổi lại latency, token và cost cao hơn baseline đáng kể. Baseline vẫn là lựa chọn tốt nhất nếu ưu tiên speed/cost/completion reliability.

Quality cần được đọc thận trọng: run `failed` không có quality score nên average quality có **survivorship bias**. Judge 0–10 cũng có **ceiling effect** vì phần lớn output hoàn thành nhận 9–10 điểm. Vì vậy conclusion không dựa riêng vào quality mà đọc cùng completion rate, citation validity, latency, tokens, cost và failure modes.

## Kết luận

- **Baseline:** tối ưu về latency, cost và tỷ lệ hoàn thành.
- **Multi-agent core:** phù hợp hơn khi strict citation compliance và auditability quan trọng; đây là variant có valid-completed rate cao nhất.
- **Multi-agent + Critic:** bounded review loop hoạt động và tạo evidence bonus, nhưng benchmark chưa cho thấy quality gain đủ ổn định để bật mặc định.
