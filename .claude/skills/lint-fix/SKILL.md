---
name: lint-fix
description: Auto-fix ruff format + lint errors in backend before committing. Run this before any git push to avoid CI/CD failures.
---

Run the following from `backend/` in order:

1. **Format (auto-fix):** `cd /home/minhdd/pet_proj/proj2/backend && uv run ruff format .`
   - Tự động reformat toàn bộ file Python theo style chuẩn

2. **Lint (auto-fix):** `uv run ruff check --fix .`
   - Fix các lỗi lint có thể tự động sửa (unused imports, v.v.)

3. **Lint check (verify):** `uv run ruff check .`
   - Kiểm tra còn lỗi nào không thể tự fix
   - Nếu còn lỗi: hiển thị rõ file:line và lý do, dừng lại và hỏi user cách xử lý

Sau khi chạy xong:
- Nếu có file bị thay đổi: báo cáo danh sách file đã được reformat/fixed
- Nếu tất cả đã clean: "✓ Backend lint clean — ruff format & check passed."
- Không tự commit hay push — chỉ fix code
