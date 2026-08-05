# Báo cáo cá nhân — Multi-Agent A2A E-commerce Dispute Resolution

## 1. Thông tin cá nhân

| Thông tin | Nội dung |
| --- | --- |
| Họ và tên | Nguyễn Duy Trọng |
| Mã học viên | 2A202601333 |
| Khóa/Lớp | K3 |
| Bài tập | E403 — Day 9 Multi-Agent A2A |
| Vai trò chính | Principal AI Engineer / Multi-Agent Pipeline Owner |
| Ngày hoàn thành | 05/08/2026 |

## 2. Mục tiêu bài làm

Xây dựng pipeline multi-agent deterministic để điều tra 50 khiếu nại thương mại điện tử trong `input/`, đối chiếu dữ liệu Olist và áp dụng `EC_POLICY_V1`. Mỗi case phải tạo một JSON có primary issue, affected entities, nguyên nhân gốc, bên chịu trách nhiệm, evidence, tài chính và hành động xử lý.

Mục tiêu kỹ thuật quan trọng nhất là tính tái lập: cùng input và CSV phải luôn sinh cùng output, không sử dụng nội dung khiếu nại làm ground truth và không tạo evidence không tồn tại.

## 3. Phạm vi công việc cá nhân

| Hạng mục | File/module liên quan | Input | Output | Trạng thái |
| --- | --- | --- | --- | --- |
| Domain model và constants | `ecommerce_dispute/domain.py` | JSON/CSV fields | Dataclass, enum, Decimal helpers | Hoàn thành |
| Data repository | `ecommerce_dispute/repository.py` | Olist CSV | Indexed order/item/payment/seller lookups | Hoàn thành |
| Domain agents | `ecommerce_dispute/agents.py` | `AgentState`, repository facts | Order, payment, delivery, policy, evidence, financial facts | Hoàn thành |
| Điều phối A2A | `ecommerce_dispute/coordinator.py` | `CustomerCase` | Verified output và trace events | Hoàn thành |
| Output và verification | `ecommerce_dispute/output.py`, `ecommerce_dispute/verifier.py` | Final agent state | Schema-compliant JSON hoặc validation error | Hoàn thành |
| Runner và artifacts | `ecommerce_dispute/runner.py` | 50 input cases | 50 output, `trace.jsonl`, `metadata.json` | Hoàn thành |
| Tests | `tests/test_policy_pipeline.py` | Real Olist cases | Policy/verifier/integration results | Hoàn thành |

## 4. Thiết kế multi-agent

Pipeline hiện tại gồm các vai trò chức năng sau:

1. `RetrieverAgent`: lấy order, item và payment rows theo `claimed_order_id`.
2. `OrderSellerAgent`: xác định entity của order và seller handoff sau shipping limit.
3. `PaymentAgent`: cộng payment rows, phát hiện split payment và đối soát tolerance 0.10 BRL.
4. `DeliveryAgent`: so sánh ngày giao thực tế với ngày giao dự kiến.
5. `PolicyAgent`: áp dụng sáu rule theo đúng thứ tự ưu tiên.
6. `EvidenceAgent`: tạo evidence ID từ các row có thật.
7. `FinancialAgent`: tính item, freight, payment và refund bằng `Decimal`.
8. `VerifierAgent`: kiểm schema, enum, ID tồn tại, policy mapping và tài chính trước khi ghi output.

`CoordinatorAgent` truyền `AgentState` bất biến giữa các agent bằng `dataclasses.replace`. Dữ liệu nghiệp vụ được truyền dưới dạng dataclass thay vì prompt hoặc text tự do.

## 5. Xử lý dữ liệu

Repository đọc và lập index cho:

- `olist_orders_dataset.csv` theo `order_id`;
- `olist_order_items_dataset.csv` theo `order_id`;
- `olist_order_payments_dataset.csv` theo `order_id`;
- `olist_sellers_dataset.csv` theo `seller_id`.

Item và payment được sắp xếp theo numeric sequence để output deterministic. Tiền được biểu diễn bằng `Decimal`, làm tròn `ROUND_HALF_UP` tới hai chữ số. `payment_value` được cộng theo từng row và không nhân với `payment_installments`.

Timestamp được parse để so sánh trực tiếp, không chuyển timezone. Seller handoff muộn khi:

```text
order_delivered_carrier_date > shipping_limit_date
```

## 6. Áp dụng EC_POLICY_V1

Policy được xét first-match theo thứ tự:

1. `canceled_order_paid` → platform, hoàn toàn bộ payment.
2. `unavailable_order_paid` → platform, hoàn toàn bộ payment.
3. `late_delivery_seller` → seller vi phạm, hoàn freight.
4. `late_delivery_logistics` → logistics provider, hoàn freight.
5. `valid_split_payment` → giải thích split payment, không hoàn tiền.
6. `unsupported_late_claim` → bác yêu cầu hoàn do giao trễ, không hoàn tiền.

Root cause, responsible party và action được ánh xạ trực tiếp từ nhánh policy đã chọn. Canceled/unavailable luôn được ưu tiên trước delivery và split payment.

## 7. Evidence và affected entities

Chỉ sử dụng năm định dạng evidence được phép:

```text
order:<order_id>
item:<order_id>:<order_item_id>
payment:<order_id>:<payment_sequential>
seller:<seller_id>
policy:<root_cause_code>
```

Mọi entity/evidence được dựng từ repository; không tạo transaction ID, refund ledger hoặc tracking checkpoint. Các danh sách được loại duplicate và giới hạn theo output schema.

## 8. Quyết định kỹ thuật quan trọng

### Chọn deterministic rule engine thay vì LLM

- **Phương án 1:** dùng LLM dưới 10B để phân tích từng case.
- **Phương án 2:** dùng Python rule engine và dataclass agents.
- **Lựa chọn:** phương án 2.

Lý do là policy đã được mô tả bằng điều kiện chính xác, còn các phép join và tài chính cần tính tái lập. Deterministic Python giảm hallucination, không cần API key và dễ audit. Metadata khai báo trung thực model `rule-engine-no-llm`, kích thước `0B`, nhỏ hơn giới hạn 10B.

## 9. Validation và kết quả chạy

Lệnh test đã chạy:

```bash
python3 -m unittest discover -s tests -v
```

Kết quả gần nhất:

```text
Ran 9 tests
OK
```

Kết quả artifacts hiện tại:

| Chỉ số | Kết quả |
| --- | ---: |
| Input cases | 50 |
| Output JSON | 50 |
| Trace events | 400 |
| Policy branches được test | 6/6 |
| Output đối chiếu lại với CSV | 50/50 đúng issue, entity, root cause, party, financial và action |
| Model parameter size | 0B |

Phân bố 50 kết luận: 8 canceled paid, 8 unavailable paid, 8 seller late, 8 logistics late, 9 valid split payment và 9 unsupported late claim.

## 10. Khó khăn và cách xử lý

### Phân biệt seller late và logistics late

Chỉ biết đơn giao sau estimate chưa đủ để gán trách nhiệm. Pipeline phải đối chiếu carrier handoff với từng `shipping_limit_date`. Nếu seller giao carrier sau hạn, seller chịu trách nhiệm; nếu seller bàn giao đúng hạn nhưng giao khách trễ, logistics chịu trách nhiệm.

### Payment có nhiều row

Không được coi installment là nhiều giao dịch hoặc nhân `payment_value` với installment. Pipeline cộng từng payment row một lần và dùng tolerance 0.10 BRL khi so sánh với item cộng freight.

### Evidence false positive

Olist không có refund transaction hay item-level tracking. Verifier tra lại order/item/payment/seller evidence trong repository và từ chối evidence không tồn tại.

## 11. Giới hạn và hướng cải tiến

Các điểm có thể cải tiến thêm mà không thay đổi kết quả 50 case hiện tại:

- Tách `OrderSellerAgent` thành `OrderAgent` và `ItemSellerAgent` độc lập.
- Bổ sung `CaseLoaderAgent`, `ArtifactAgent` và message envelope đầy đủ cho từng handoff.
- Chạy song song các bước order/item/payment.
- Để Verifier tự chạy lại toàn bộ điều kiện policy thay vì chỉ kiểm mapping của kết luận.
- Rule logistics cần khẳng định carrier timestamp và mọi shipping limit đều tồn tại.
- Rule unsupported claim cần kiểm rõ cả delivery within estimate và payment reconciliation thay vì dùng nhánh mặc định.
- Tăng test coverage cho missing timestamp, payment mismatch, duplicate ID, exact input set và trace overwrite.
- Sinh runtime metadata từ môi trường thực tế thay vì hard-code phiên bản Python.

## 12. Hướng dẫn tái lập

```bash
# Chạy tests
python3 -m unittest discover -s tests -v

# Chạy đủ pipeline
python3 -m ecommerce_dispute.runner \
  --input-dir input \
  --output-dir output \
  --data-dir data \
  --trace-path trace.jsonl \
  --metadata-path metadata.json

# Đóng gói theo định dạng portal đang chấp nhận
zip -r output.zip output
```

## 13. Cam kết cá nhân

- [x] Báo cáo phản ánh đúng implementation và kết quả đã kiểm chứng.
- [x] Tôi có thể giải thích luồng end-to-end và các rule nghiệp vụ.
- [x] Không ghi nhận bước chưa chạy là đã thành công.
- [x] Không chứa `.env`, API key, token hoặc secret.
- [x] Không sử dụng model vượt quá 10B parameters.
- [x] Không tạo evidence hoặc dữ liệu không tồn tại trong Olist.

**Họ và tên:** Nguyễn Duy Trọng  
**Mã học viên:** 2A202601333  
**Ngày xác nhận:** 05/08/2026
