# Báo cáo cá nhân — Day 9 Multi-Agent A2A

## 1. Thông tin cá nhân

| Thông tin | Nội dung |
| --- | --- |
| Họ và tên | Nguyễn Hoàng Tín |
| Mã học viên | 2A202601603 |
| 5 số cuối mã học viên | 01603 |
| Khóa/Lớp | K3 |
| Bài tập | E403 — Multi-Agent E-commerce Dispute Resolution |
| Vai trò chính | Thành viên / Kiểm thử, review output và tính nhất quán báo cáo |
| Ngày hoàn thành | 05/08/2026 |

## 2. Bối cảnh và mục tiêu bài làm

Đây là bài tập nhóm xây dựng hệ thống multi-agent để xử lý 50 khiếu nại thương mại điện tử. Mỗi case cung cấp một `claimed_order_id`; hệ thống phải đối chiếu đơn hàng, item, seller, payment và các mốc giao hàng trong dữ liệu Olist, sau đó áp dụng `EC_POLICY_V1` để xác định vấn đề, nguyên nhân, bên chịu trách nhiệm, bằng chứng, khoản hoàn đề xuất và hành động xử lý.

Hệ thống của nhóm sử dụng các Python agent deterministic, không gọi LLM trong quá trình chấm case. Cách làm này phù hợp với bài toán có policy rõ ràng, cần số tiền và evidence chính xác, đồng thời tránh tạo ra dữ liệu không tồn tại trong CSV.

## 3. Vai trò và phạm vi công việc

### Phần việc phụ trách

| Hạng mục | File/artifact liên quan | Input nhận vào | Output bàn giao | Trạng thái |
| --- | --- | --- | --- | --- |
| Review output chính thức | `input/EC_*.json`, `output/EC_*.json` | 50 input và output tương ứng | Nhận xét về schema, entity, evidence và số tiền | Hoàn thành |
| Kiểm thử quy tắc nghiệp vụ | `tests/test_system.py` | Sáu policy rule và các edge case | Kết quả unit test và xác nhận nhánh xử lý | Hoàn thành |
| Kiểm tra submission | `scripts/validate_outputs.py` | 50 output, CSV và artifacts | Báo cáo validator PASS/FAIL | Hoàn thành |
| Review tính nhất quán tài liệu | `README.md`, `architecture.md`, báo cáo cá nhân | Kiến trúc và implementation hiện tại | Góp ý để mô tả đúng luồng thực tế | Hoàn thành |

Tôi không nhận ownership cho toàn bộ pipeline. Phần đóng góp chính của tôi là kiểm thử, đối chiếu kết quả, rà soát edge case và giúp nhóm bảo đảm tài liệu phản ánh đúng hệ thống đang chạy.

### Hỗ trợ nhóm

| Hoạt động | Module/thành viên được hỗ trợ | Kết quả |
| --- | --- | --- |
| Review kết quả theo policy | Pipeline chung của nhóm | Xác nhận output bám sáu nhánh `EC_POLICY_V1` |
| Kiểm tra các trường dễ mất điểm | Evidence, affected entities, financial resolution | Phát hiện rủi ro từ ID không tồn tại, cộng payment sai và refund không khớp status |
| Đối chiếu báo cáo | Báo cáo nhóm và báo cáo cá nhân | Thống nhất thuật ngữ, tên artifact và kết quả kiểm thử |

## 4. Hiểu biết về kiến trúc multi-agent

Luồng xử lý một case như sau:

```text
Input JSON
   ↓
CaseLoaderAgent
   ↓
OrderAgent ─┐
ItemSellerAgent ─┼→ DeliveryAgent → PolicyAgent
PaymentAgent ────┘                       │
                              ┌──────────┴──────────┐
                              ↓                     ↓
                       EvidenceAgent         FinancialAgent
                              └──────────┬──────────┘
                                         ↓
                                  VerifierAgent
                                         ↓
                                    Output JSON
```

`SupervisorAgent` điều phối các bước và ghi trace handoff. Order, item/seller và bước tải payment có thể chạy song song vì chúng cùng bắt đầu từ `claimed_order_id`. Delivery phải chờ order và item facts; Policy phải chờ delivery và payment; Evidence và Financial chỉ chạy sau khi đã có quyết định policy.

Các agent truyền dữ liệu có cấu trúc bằng dataclass như `OrderFacts`, `ItemSellerFacts`, `PaymentFacts`, `DeliveryFacts` và `PolicyDecision`. Việc này làm contract giữa các agent rõ ràng và dễ kiểm thử hơn so với truyền nội dung tự do.

## 5. Quy tắc nghiệp vụ đã kiểm tra

Policy sử dụng cơ chế first-match theo đúng thứ tự:

1. `canceled_order_paid`: đơn bị hủy và đã thanh toán; platform chịu trách nhiệm; hoàn toàn bộ payment.
2. `unavailable_order_paid`: đơn unavailable và đã thanh toán; platform chịu trách nhiệm; hoàn toàn bộ payment.
3. `late_delivery_seller`: giao khách trễ và seller bàn giao carrier sau hạn; hoàn freight.
4. `late_delivery_logistics`: giao khách trễ nhưng seller bàn giao đúng hạn; logistics chịu trách nhiệm; hoàn freight.
5. `valid_split_payment`: có ít nhất hai payment row và tổng payment khớp item cộng freight trong sai số 0.10 BRL; không hoàn.
6. `unsupported_late_claim`: giao không trễ và payment khớp; bác yêu cầu hoàn do giao trễ.

Thứ tự này quan trọng. Ví dụ, nếu một đơn đã thanh toán rồi bị hủy và đồng thời có dấu hiệu liên quan đến giao hàng, nhánh canceled vẫn phải được chọn trước.

## 6. Các điểm kiểm thử quan trọng

### Đối soát thanh toán

Tổng thanh toán được tính bằng cách cộng từng `payment_value` đúng một lần:

```text
payment_total = sum(payment_value của từng payment row)
order_total = item_total + freight_total
```

Không nhân `payment_value` với `payment_installments`. Sai số đối soát được chấp nhận tối đa là `0.10 BRL`.

### Xác định trách nhiệm giao trễ

Chỉ việc khách nhận hàng sau ngày dự kiến chưa đủ để kết luận seller có lỗi. Cần kiểm tra thêm:

```text
order_delivered_carrier_date > shipping_limit_date
```

Nếu điều kiện đúng, seller bàn giao muộn. Nếu seller bàn giao đúng hạn nhưng khách nhận sau estimated date, trách nhiệm thuộc logistics provider.

### Evidence

Chỉ chấp nhận năm namespace:

```text
order:<order_id>
item:<order_id>:<order_item_id>
payment:<order_id>:<payment_sequential>
seller:<seller_id>
policy:<root_cause_code>
```

Verifier phải tra lại sự tồn tại của order, item, payment và seller. Không được tự tạo refund transaction, tracking checkpoint hoặc bằng chứng giao thiếu vì dataset không cung cấp các dữ liệu đó.

### Tài chính và trạng thái case

- Refund lớn hơn 0 phải đi cùng `action_required`.
- Refund bằng 0 phải đi cùng `no_action`.
- Đơn canceled/unavailable được hoàn `payment_total`.
- Giao trễ do seller/logistics được hoàn `freight_total`.
- Mọi phép tính tiền dùng `Decimal` và làm tròn hai chữ số.

## 7. Một quyết định kỹ thuật quan trọng

- **Bối cảnh:** Policy của đề là sáu điều kiện định lượng, trong khi output bị chấm chặt về ID, số tiền và enum.
- **Phương án 1:** Dùng LLM dưới 10B để đọc facts và tự suy luận kết quả.
- **Phương án 2:** Dùng các agent Python deterministic với contract rõ ràng và verifier độc lập.
- **Phương án được chọn:** Agent Python deterministic.
- **Lý do:** Kết quả tái lập, không cần API key, giảm hallucination và dễ đối chiếu với CSV. Metadata khai báo trung thực `deterministic-python-rules-v1`, kích thước `0B (no LLM)`.
- **Trade-off:** Hệ thống không khai thác sâu nội dung ngôn ngữ tự nhiên trong lời khiếu nại; quyết định dựa trên `claimed_order_id` và dữ liệu có thể kiểm chứng.

## 8. Lỗi và rủi ro đã rà soát

### Rủi ro: nhầm split payment với installment

- **Triệu chứng:** Tổng payment có thể bị tính quá lớn nếu lấy `payment_value * payment_installments`.
- **Nguyên nhân:** Hiểu sai ý nghĩa của `payment_installments` trong Olist.
- **Cách xử lý:** Cộng mỗi payment row đúng một lần; chỉ dùng số lượng row để xác định split payment.
- **Cách xác minh:** Test `test_11_multiple_payment_rows_not_installment_multiplied` chạy thành công.

### Rủi ro: evidence false positive

- **Triệu chứng:** Output chứa evidence đúng định dạng nhưng không tồn tại trong CSV.
- **Nguyên nhân:** Chỉ kiểm regex mà không kiểm referential integrity.
- **Cách xử lý:** `VerifierAgent` gọi repository để xác nhận từng order/item/payment/seller.
- **Cách xác minh:** Các test evidence sai định dạng và evidence không tồn tại đều được verifier từ chối.

## 9. Cách xác minh và kết quả thực tế

Các lệnh đã dùng để kiểm tra hệ thống:

```bash
python -m unittest discover -s tests -v
python scripts/validate_outputs.py
```

Kết quả thực tế:

```text
Ran 20 tests
OK

Cases expected: 50
Cases generated: 50
Schema passed: 50
Business rules passed: 50
Evidence passed: 50
Financial checks passed: 50
Submission status: PASS
```

Các test bao phủ sáu nhánh policy, tolerance 0.10, đơn không có item, nhiều item/payment, evidence, cardinality, confidence, schema, enum, policy priority và trace overwrite.

## 10. Hiểu biết end-to-end

1. `CaseLoaderAgent` lấy `claimed_order_id` từ input và kiểm tra policy version.
2. Repository dùng ID này để tra order, item, seller và payment trong dữ liệu Olist.
3. Các domain agent chuyển raw rows thành facts có cấu trúc và tính các tổng tiền, mốc giao hàng.
4. `PolicyAgent` chọn đúng một primary issue theo thứ tự ưu tiên.
5. `EvidenceAgent` và `FinancialAgent` tạo bằng chứng và phương án tài chính.
6. `SupervisorAgent` dựng draft output.
7. `VerifierAgent` độc lập kiểm tra schema, policy, entity, evidence, confidence và tài chính.
8. Chỉ draft đạt PASS mới được ghi atomically vào `output/`; mọi handoff được ghi vào `trace.jsonl`.

Chất lượng của bài được xác định chủ yếu bởi tính đúng đắn của dữ liệu có cấu trúc: issue, entity ID, root cause, responsible party, evidence, số tiền và action. Nội dung lời giải tự nhiên không phải đầu ra chấm điểm chính.

## 11. Giới hạn và đề xuất cải tiến

- Cần xác nhận với giảng viên việc sử dụng rule engine `0B` có đáp ứng yêu cầu “model không quá 10B” hay bắt buộc phải gọi LLM thật.
- Artifact hiện được sinh ở root repository; nên thống nhất rõ với yêu cầu về vị trí `logging/` trước khi nộp.
- Có thể bổ sung báo cáo coverage tự động và thống kê phân bố sáu primary issue.
- Có thể thêm kiểm tra ZIP cuối cùng để chắc chắn archive chỉ chứa đúng 50 JSON ở cấp root.

## 12. Cam kết cá nhân

- [x] Báo cáo phản ánh đúng vai trò kiểm thử và review của tôi.
- [x] Tôi hiểu luồng end-to-end, không chỉ phần kiểm thử.
- [x] Tôi chỉ ghi nhận kết quả đã được chạy và kiểm chứng.
- [x] Báo cáo không chứa `.env`, API key, token hoặc secret.
- [x] Tôi không nhận ownership cho phần việc do thành viên khác trực tiếp triển khai.
- [x] Tôi không tạo hoặc chấp nhận evidence không tồn tại trong Olist.

**Họ và tên:** Nguyễn Hoàng Tín  
**Mã học viên:** 2A202601603  
**Ngày xác nhận:** 05/08/2026
