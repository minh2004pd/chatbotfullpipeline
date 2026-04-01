"""
Cấu hình structlog để log ra cả console và file.
Logs được lưu tại folder `logs/` với prefix theo timestamp.
"""

import logging
import sys
from datetime import datetime
from pathlib import Path

import structlog
from structlog.types import Processor

# Thư mục chứa logs
LOG_DIR = Path("logs")


def setup_logging():
    """Khởi tạo cấu hình logging cho ứng dụng."""

    # Đảm bảo thư mục logs tồn tại
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    # Tên file log theo thời điểm chạy: app_20240331_151400.log
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = LOG_DIR / f"app_{timestamp}.log"

    # Shared processors cho cả console và file
    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    # Cấu hình chuẩn cho logging module (để bắt được logs của các thư viện khác)
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=logging.INFO,
    )

    structlog.configure(
        processors=shared_processors
        + [
            structlog.processors.CallsiteParameterAdder(
                {
                    structlog.processors.CallsiteParameter.FILENAME,
                    structlog.processors.CallsiteParameter.FUNC_NAME,
                    structlog.processors.CallsiteParameter.LINENO,
                }
            ),
            # Wrapper này cho phép gửi log đến nhiều handlers của stdlib logging
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Handlers cho standard logging
    # 1. Console handler (đẹp, dễ nhìn)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            processor=structlog.dev.ConsoleRenderer(colors=True),
        )
    )

    # 2. File handler (ổn định, lưu trữ)
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            processor=structlog.processors.JSONRenderer(),  # File dùng JSON cho dễ parse
        )
    )

    # Cấu hình root logger của Python để dùng các handlers này
    root_logger = logging.getLogger()
    root_logger.handlers = [console_handler, file_handler]
    root_logger.setLevel(logging.INFO)

    # Giảm nhiễu từ các thư viện lớn
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("boto3").setLevel(logging.WARNING)
    logging.getLogger("botocore").setLevel(logging.WARNING)

    # Log khởi tạo
    logger = structlog.get_logger(__name__)
    logger.info("logging_initialized", log_file=str(log_file))
