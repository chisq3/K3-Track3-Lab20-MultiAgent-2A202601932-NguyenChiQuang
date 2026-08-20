# Báo cáo Benchmark Offline có Kiểm soát

Ngày tạo benchmark: 2026-08-20

## Thiết lập Thí nghiệm

- Model: `openai/gpt-4o-mini`.
- LLM endpoint: `https://openrouter.ai/api/v1`.
- Retrieval provider: subset corpus offline do lab cung cấp; các kiến trúc nghiên cứu không gọi Tavily hoặc live web retrieval.
- Temperature: baseline 0.2; Researcher 0.2; Analyst 0.1; Writer 0.4; Critic 0.0; blind quality judge 0.0.
- Cost ưu tiên provider-reported usage từ OpenRouter; nếu provider cost không đầy đủ thì ghi `n/a`, không tự áp giá của provider khác.

### Bộ test

| Case | Query | Đối tượng | Số nguồn tối đa |
|---|---|---|---:|
| AIAGENT-01 | When does a multi-agent architecture produce better research reports than a single capable agent, after accounting for quality, cost, latency, and coordination failure? | AI researchers, agent-system engineers, evaluation teams, and technical decision makers | 5 |
| AIAGENT-12 | How should verifier agents check claims, citations, calculations, and logical consistency without becoming redundant with the primary researcher? | AI researchers, agent-system engineers, evaluation teams, and technical decision makers | 5 |
| AIAGENT-22 | How should a multi-agent system trade off more agents and parallel searches against inference cost, latency, and marginal quality improvement? | AI researchers, agent-system engineers, evaluation teams, and technical decision makers | 5 |

## Thiết lập Corpus Offline

- Topic được chọn: `AIAGENT-01, AIAGENT-12, AIAGENT-22`.
- Phiên bản corpus: `2.0-rich-offline`.
- Evidence dùng cho citation lấy từ `knowledge_base.source_documents` của từng topic.
- Retrieval dùng lexical ranking deterministic với `max_sources=5`.
- Synthetic document luôn giữ nhãn rõ trong metadata và prompt evidence.
- URL `https://offline.local/...` là benchmark locator ổn định, không phải live web page.
- LLM provider và LangSmith tracing vẫn có thể online; chỉ research retrieval là offline và cố định.

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
| baseline | 6 | 100% | 13.93 | 3228 | 0.000800 | 10.00 | 33% | 33% | 1.0 | 0.00 |
| multi-agent | 6 | 67% | 39.12 | 13376 | 0.002657 | 10.00 | 34% | 100% | 4.5 | 0.00 |
| multi-agent-critic | 6 | 33% | 46.03 | 18446 | 0.003067 | 10.00 | 32% | 100% | 5.5 | 0.00 |

## Trade-off Quan sát được

- Multi-agent so với baseline: latency +181.0%, tokens +314.4%, quality +0.00 points, citation coverage +0.8 điểm phần trăm.
- Critic so với core multi-agent: latency +17.6%, tokens +37.9%, quality +0.00 points, citation coverage -1.9 điểm phần trăm.

## Kết quả Từng Run

| Kiến trúc | Query | Repeat | Trạng thái | Latency (s) | Tokens | Cost | Quality | Citation coverage | Hợp lệ | Retries | Revisions | Lý do dừng | Trace |
|---|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| baseline | AIAGENT-01 | 1 | completed | 12.48 | 3128 | 0.000796 | 10.00 | 37% | 0% | 0 | 0 | completed | [trace](https://smith.langchain.com/o/0e2fbfaf-b11b-43a8-a13d-dd195ec58964/projects/p/a205b094-b4a3-4f15-a5c0-528321a0e6d4/r/01a01f3e-6921-76f2-986c-81489d0ee55c?poll=true) |
| multi-agent | AIAGENT-01 | 1 | completed | 42.30 | 15822 | 0.002785 | 10.00 | 40% | 100% | 1 | 0 | completed | [trace](https://smith.langchain.com/o/0e2fbfaf-b11b-43a8-a13d-dd195ec58964/projects/p/a205b094-b4a3-4f15-a5c0-528321a0e6d4/r/01a01f3e-a75d-7b63-97aa-e39409c4a878?poll=true) |
| multi-agent-critic | AIAGENT-01 | 1 | partial | 40.85 | 20924 | 0.003348 | 10.00 | 33% | 100% | 1 | 0 | critic_failed | [trace](https://smith.langchain.com/o/0e2fbfaf-b11b-43a8-a13d-dd195ec58964/projects/p/a205b094-b4a3-4f15-a5c0-528321a0e6d4/r/01a01f3f-79e3-7c53-8bfa-78cff7c7e57b?poll=true) |
| baseline | AIAGENT-12 | 1 | completed | 13.75 | 3264 | 0.000887 | 10.00 | 36% | 0% | 0 | 0 | completed | [trace](https://smith.langchain.com/o/0e2fbfaf-b11b-43a8-a13d-dd195ec58964/projects/p/a205b094-b4a3-4f15-a5c0-528321a0e6d4/r/01a01f40-3b52-7742-a2d6-810165a37e6f?poll=true) |
| multi-agent | AIAGENT-12 | 1 | failed | 40.59 | 15624 | 0.003564 | n/a | n/a | n/a | 1 | 0 | writer_failed | [trace](https://smith.langchain.com/o/0e2fbfaf-b11b-43a8-a13d-dd195ec58964/projects/p/a205b094-b4a3-4f15-a5c0-528321a0e6d4/r/01a01f40-7b90-7cc0-a5c0-9e88dacac71b?poll=true) |
| multi-agent-critic | AIAGENT-12 | 1 | failed | 40.98 | 15804 | 0.002975 | n/a | n/a | n/a | 1 | 0 | writer_failed | [trace](https://smith.langchain.com/o/0e2fbfaf-b11b-43a8-a13d-dd195ec58964/projects/p/a205b094-b4a3-4f15-a5c0-528321a0e6d4/r/01a01f41-1a1b-7f02-a412-75c30ba5b348?poll=true) |
| baseline | AIAGENT-22 | 1 | completed | 13.93 | 3332 | 0.000914 | 10.00 | 30% | 100% | 0 | 0 | completed | [trace](https://smith.langchain.com/o/0e2fbfaf-b11b-43a8-a13d-dd195ec58964/projects/p/a205b094-b4a3-4f15-a5c0-528321a0e6d4/r/01a01f41-ba32-7162-97e1-9dc2a8b3d57c?poll=true) |
| multi-agent | AIAGENT-22 | 1 | completed | 33.11 | 11309 | 0.002659 | 10.00 | 33% | 100% | 0 | 0 | completed | [trace](https://smith.langchain.com/o/0e2fbfaf-b11b-43a8-a13d-dd195ec58964/projects/p/a205b094-b4a3-4f15-a5c0-528321a0e6d4/r/01a01f41-fa31-7991-9112-06db3fb0e3c9?poll=true) |
| multi-agent-critic | AIAGENT-22 | 1 | completed | 39.52 | 20845 | 0.003291 | 10.00 | 28% | 100% | 1 | 0 | completed | [trace](https://smith.langchain.com/o/0e2fbfaf-b11b-43a8-a13d-dd195ec58964/projects/p/a205b094-b4a3-4f15-a5c0-528321a0e6d4/r/01a01f42-84ee-78d2-be04-728016b34b15?poll=true) |
| multi-agent | AIAGENT-01 | 2 | failed | 48.92 | 15089 | 0.002690 | n/a | n/a | n/a | 1 | 0 | writer_failed | [trace](https://smith.langchain.com/o/0e2fbfaf-b11b-43a8-a13d-dd195ec58964/projects/p/a205b094-b4a3-4f15-a5c0-528321a0e6d4/r/01a01f43-2a4a-7c92-8f9b-93bdfee3c117?poll=true) |
| multi-agent-critic | AIAGENT-01 | 2 | partial | 43.31 | 21372 | 0.003282 | 10.00 | 37% | 100% | 1 | 0 | critic_failed | [trace](https://smith.langchain.com/o/0e2fbfaf-b11b-43a8-a13d-dd195ec58964/projects/p/a205b094-b4a3-4f15-a5c0-528321a0e6d4/r/01a01f43-e961-72c2-a86b-21c15bdc5867?poll=true) |
| baseline | AIAGENT-01 | 2 | completed | 12.58 | 3162 | 0.000644 | 10.00 | 42% | 0% | 0 | 0 | completed | 01a01f44-a154-7df0-85c8-9fb1d59a6d30 |
| multi-agent | AIAGENT-12 | 2 | completed | 35.10 | 11300 | 0.002167 | 10.00 | 33% | 100% | 0 | 0 | completed | [trace](https://smith.langchain.com/o/0e2fbfaf-b11b-43a8-a13d-dd195ec58964/projects/p/a205b094-b4a3-4f15-a5c0-528321a0e6d4/r/01a01f44-e1a7-7380-b1c1-3fbb9ec20a3d?poll=true) |
| multi-agent-critic | AIAGENT-12 | 2 | failed | 63.31 | 15700 | 0.002815 | n/a | n/a | n/a | 1 | 0 | timeout | [trace](https://smith.langchain.com/o/0e2fbfaf-b11b-43a8-a13d-dd195ec58964/projects/p/a205b094-b4a3-4f15-a5c0-528321a0e6d4/r/01a01f45-73fd-79b1-92ca-38f0d128d596?poll=true) |
| baseline | AIAGENT-12 | 2 | completed | 12.42 | 3155 | 0.000648 | 10.00 | 27% | 0% | 0 | 0 | completed | 01a01f46-6b46-78e3-a112-743b1d3675f6 |
| multi-agent | AIAGENT-22 | 2 | completed | 34.73 | 11109 | 0.002075 | 10.00 | 30% | 100% | 0 | 0 | completed | [trace](https://smith.langchain.com/o/0e2fbfaf-b11b-43a8-a13d-dd195ec58964/projects/p/a205b094-b4a3-4f15-a5c0-528321a0e6d4/r/01a01f46-abdd-7061-a69f-f17469103151?poll=true) |
| multi-agent-critic | AIAGENT-22 | 2 | completed | 48.18 | 16029 | 0.002689 | 10.00 | 31% | 100% | 0 | 0 | completed | [trace](https://smith.langchain.com/o/0e2fbfaf-b11b-43a8-a13d-dd195ec58964/projects/p/a205b094-b4a3-4f15-a5c0-528321a0e6d4/r/01a01f47-3bce-7740-9d09-2fe655862aff?poll=true) |
| baseline | AIAGENT-22 | 2 | completed | 18.40 | 3326 | 0.000911 | 10.00 | 29% | 100% | 0 | 0 | completed | [trace](https://smith.langchain.com/o/0e2fbfaf-b11b-43a8-a13d-dd195ec58964/projects/p/a205b094-b4a3-4f15-a5c0-528321a0e6d4/r/01a01f48-013b-70b0-8abd-3df5c8835c53?poll=true) |

## Phân tích Failure

| Kiến trúc | Query | Repeat | Trạng thái | Lý do dừng | Ghi chú |
|---|---|---:|---|---|---|
| multi-agent-critic | AIAGENT-01 | 1 | partial | critic_failed | Quyết định `revise` của Critic phải kèm ít nhất một vấn đề cần sửa; Quyết định `revise` của Critic phải kèm ít nhất một vấn đề cần sửa |
| multi-agent | AIAGENT-12 | 1 | failed | writer_failed | Phần Sources chứa URL của nguồn không được trích dẫn; Phần Sources chứa URL của nguồn không được trích dẫn |
| multi-agent-critic | AIAGENT-12 | 1 | failed | writer_failed | Phần Sources chứa URL của nguồn không được trích dẫn; Phần Sources chứa URL của nguồn không được trích dẫn |
| multi-agent | AIAGENT-01 | 2 | failed | writer_failed | Phần Sources chứa URL của nguồn không được trích dẫn; Phần Sources chứa URL của nguồn không được trích dẫn |
| multi-agent-critic | AIAGENT-01 | 2 | partial | critic_failed | Quyết định `revise` của Critic phải kèm ít nhất một vấn đề cần sửa; Quyết định `revise` của Critic phải kèm ít nhất một vấn đề cần sửa |
| multi-agent-critic | AIAGENT-12 | 2 | failed | timeout | Phần Sources chứa URL của nguồn không được trích dẫn; Phần Sources chứa URL của nguồn không được trích dẫn |

## Ghi chú Diễn giải

Không giả định multi-agent luôn tốt hơn. Kiến trúc đắt hơn chỉ hợp lý khi lợi ích về grounding, citation, auditability hoặc failure handling đủ quan trọng với bài toán mục tiêu.

Kết quả Critic trong workflow chỉ mang tính diagnostic. Cột quality aggregate dùng independent blind judge, vì vậy Critic không tự chấm điểm cho chính variant của mình.

## Diễn giải End-to-End

Vì retrieval evidence được cố định, controlled benchmark giúp kiểm tra liệu khác biệt kiến trúc có còn tồn tại khi loại bỏ Tavily variance.

| Kiến trúc | Valid completed offline |
|---|---:|
| Baseline | 2/6 = 33.3% |
| Multi-agent core | **4/6 = 66.7%** |
| Multi-agent + Critic | 2/6 = 33.3% |

Kết quả này củng cố insight của benchmark online: core multi-agent có khả năng enforce strict citation compliance tốt hơn trên các output end-to-end, dù completion reliability và efficiency thấp hơn baseline.

Quality của các output chấm được đều gần trần 10/10, nên controlled experiment không dùng quality làm yếu tố phân biệt chính. Các metric có ý nghĩa hơn ở đây là valid-completed rate, citation validity, failure behavior, latency, tokens và cost.

## Kết luận

- Fixed evidence không làm core multi-agent mất lợi thế về strict citation-valid completion.
- Baseline tiếp tục là kiến trúc nhanh/rẻ/ổn định nhất về completion.
- Critic tạo thêm review nhưng đồng thời thêm structured-output contract, token và failure surface; giữ Critic là optional mode là phù hợp với dữ liệu.
