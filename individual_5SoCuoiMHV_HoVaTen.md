# Báo cáo cá nhân — Olist Multi-Agent Dispute Resolution

## 1. Thông tin cá nhân

| Thông tin | Nội dung |
|---|---|
| Họ và tên | `[Họ và tên — chưa được cung cấp]` |
| MSSV | `[MSSV — chưa được cung cấp]` |
| Khóa/Lớp | K3 |
| Vai trò chính | Principal AI Engineer / Senior Python Engineer |
| Ngày hoàn thành | 2026-08-05 |

Placeholder danh tính được giữ rõ ràng vì repository không cung cấp họ tên hoặc MSSV; báo cáo không tự bịa thông tin cá nhân.

## 2. Mục tiêu và phạm vi công việc

Mục tiêu là xây hệ thống multi-agent thật để điều tra 50 khiếu nại Olist theo `EC_POLICY_V1`, chỉ dựa trên bằng chứng CSV, sinh đúng schema, trace A2A và package chỉ chứa output hợp lệ.

| Module/deliverable | File phụ trách | Input | Output | Trạng thái |
|---|---|---|---|---|
| Contracts/infrastructure | `core/`, `data_access/` | 9 CSV, dataclass contracts | repository read-only, Decimal, trace | Hoàn thành |
| Domain agents | `agents/*.py` | case/facts theo domain | typed facts/decision/evidence/finance | Hoàn thành |
| Orchestration | `agents/supervisor.py` | một case | verified final JSON | Hoàn thành |
| Hard gates | `agents/verifier_agent.py` | raw facts + draft | `VerificationResult` | Hoàn thành |
| CLI/validation/package | `scripts/` | toàn repo | 50 output, validation, ZIP | Hoàn thành |
| Test và tài liệu | `tests/`, `architecture.md` | requirements | 20 test, kiến trúc audit được | Hoàn thành |

## 3. Thiết kế agent và A2A

`SupervisorAgent` chỉ điều phối. `CaseLoaderAgent` xác thực input. Ba domain extractor `OrderAgent`, `ItemSellerAgent`, `PaymentAgent` dùng query surface tách biệt và được dispatch song song. `DeliveryAgent` nhận facts đã chuẩn hóa; `PolicyAgent` áp dụng sáu rule first-match. `EvidenceAgent` chỉ dựng ID cho row/policy thật và `FinancialAgent` tính tiền độc lập bằng Decimal. `VerifierAgent` không gọi `PolicyAgent`: nó tự tính lại payment match, delivery lateness, seller handoff, policy priority, refund và referential integrity. `ArtifactAgent` chỉ quản lý metadata/trace-level artifacts.

Mỗi dispatch tạo `AgentMessage` có message ID, sender/recipient, task, status, input refs, payload summary, errors và timestamp. Trace cuối có 2.405 JSONL events: 550 supervisor dispatch, 551 agent start/result/handoff (bao gồm ArtifactAgent), 50 verification pass và 50 atomic output write.

## 4. Xử lý dữ liệu và quyết định kỹ thuật

- Xác thực đúng chín CSV và header trước khi chạy; business path chỉ tải bảng cần cho policy.
- Không nhân `payment_value` với installment; tổng mọi payment row bằng Decimal.
- So sánh timestamp nguyên văn như CSV, không đổi timezone.
- Với order nhiều item, seller late khi carrier date lớn hơn shipping limit của item seller đó.
- Policy dừng ở rule đầu match để canceled/unavailable luôn ưu tiên delivery/split.
- Output sort theo case, item/payment sort theo sequence; JSON cấm NaN/Infinity.
- Confidence không ngẫu nhiên: 0.95 cho multi-row hoàn chỉnh, 0.97 khi có null không thiết yếu, 0.99 khi dữ liệu đơn giản và đầy đủ.
- Output ghi qua temp file và `os.replace`, chỉ sau Verifier PASS.

## 5. Một quyết định kỹ thuật quan trọng

- **Bối cảnh:** Case classification có thể dùng LLM hoặc rule engine.
- **Phương án cân nhắc:** (1) LLM dưới 10B qua provider; (2) deterministic Python với agent contracts.
- **Phương án chọn:** deterministic Python (`deterministic-python-rules-v1`, 0B/no LLM).
- **Lý do:** policy đóng, dữ liệu có cấu trúc và yêu cầu reproducibility cao; Decimal + explicit first-match dễ audit hơn, không cần secret/network và không có hallucination evidence.
- **Bằng chứng:** 20/20 unit tests và validator độc lập 50/50 PASS; sáu nhóm rule đều xuất hiện trong output.

## 6. Validation và lỗi đã xử lý

Các gate bao gồm exact schema/type, enum, cardinality, referential integrity, business priority, independent financial sums, refund/status consistency, deterministic confidence và evidence format/existence/relevance.

Trong audit sau lần validation đầu, Verifier được phát hiện vẫn dùng hai boolean đã dẫn xuất từ `PaymentAgent`/`DeliveryAgent`. Đây không làm sai output nhưng giảm tính độc lập của hard gate. Cách xử lý là sửa Verifier tự cộng payment/item/freight và tự so sánh timestamp/shipping limit từ row facts. Sau thay đổi đã chạy lại compile, 20 test, full 50 case và validator; tất cả tiếp tục PASS.

## 7. Kết quả chạy thật

| Chỉ số | Kết quả |
|---|---:|
| Input hợp lệ | 50/50 |
| Unit tests | 20 pass, 0 fail |
| Output sinh | 50/50 |
| Schema gate | 50/50 |
| Business rules | 50/50 |
| Evidence gate | 50/50 |
| Financial gate | 50/50 |
| Submission validator | PASS |

Phân bố kết luận: 8 canceled-paid, 8 unavailable-paid, 8 late-seller, 8 late-logistics, 9 valid split-payment và 9 unsupported late claim. Có 32 case `action_required` và 18 case `no_action`.

## 8. Khó khăn, bài học và hướng cải tiến

Khó khăn chính là giữ ranh giới agent trong khi Payment cần totals của Item và ItemSeller cần carrier date của Order. Giải pháp là tách bước fetch song song khỏi bước enrichment/reconciliation có structured handoff. Bài học quan trọng là “Verifier độc lập” phải tính lại raw predicate, không chỉ so sánh enum cuối.

Hướng cải tiến: streaming index cho dataset lớn hơn; schema bằng Pydantic/JSON Schema nếu dependency được phép; fault-injection tests cho retry routing; hash manifest cho CSV/input; và process-level parallelism cho hàng triệu case. Các cải tiến này không cần cho bộ 50 case hiện tại.

## 9. Hướng dẫn tái lập

```bash
# Không có dependency ngoài standard library
python3 -m unittest discover -s tests -v
python3 scripts/run_all.py
python3 scripts/validate_outputs.py
python3 scripts/package_submission.py
```

Artifacts kiểm tra: `trace.jsonl`, `metadata.json`, 50 file trong `output/` và `submission_outputs.zip`.

## 10. Cam kết

- [x] Nội dung phản ánh đúng phần kỹ thuật đã thực hiện và kiểm chứng.
- [x] Không tuyên bố thành công cho bước chưa chạy.
- [x] Không chứa `.env`, API key, token hoặc secret.
- [x] Không sử dụng claim làm ground truth và không tạo evidence giả.
- [x] Placeholder danh tính được giữ vì chưa có dữ liệu thật.

**Họ và tên:** `[Họ và tên — chưa được cung cấp]`
**Ngày xác nhận:** 2026-08-05
