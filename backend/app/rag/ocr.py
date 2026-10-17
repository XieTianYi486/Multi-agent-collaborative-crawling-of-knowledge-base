# ============================================================
# OCR 引擎（RapidOCR）
# 用于 PDF 扫描件/图片页的文字识别
#
# 设计要点：
# - 懒加载单例：rapidocr_onnxruntime 的 import 放在 __init__ 内，
#   未安装 OCR 依赖的环境 import 本模块不会崩；
# - 只在"页面文本层为空"时被 parse_pdf 调用，正常文本 PDF 零开销；
# - OCR 不可用时返回空文本并告警，文档最终走既有的
#   "文档内容为空"异常路径，不新增失败模式。
# ============================================================

import logging
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

# OCR 引擎单例（懒加载）
_engine = None
_engine_failed = False

# 扫描页判定阈值：文本层字符数低于该值视为扫描页/图片页
MIN_TEXT_CHARS = 20


def ocr_available() -> bool:
    """OCR 引擎是否可用（不触发加载）。"""
    global _engine, _engine_failed
    if _engine is not None:
        return True
    if _engine_failed:
        return False
    return True


def ocr_page_image(pixmap_bytes: bytes, width: int, height: int) -> str:
    """
    对单页渲染图像执行 OCR，返回识别文本（按行拼接）。

    参数:
        pixmap_bytes: PyMuPDF page.get_pixmap(...).samples 原始像素
        width/height: 图像尺寸（像素）
        (nbytes 应等于 width * height * n，n 为每像素通道数)

    返回:
        识别出的文本；OCR 不可用/失败返回 ""
    """
    global _engine, _engine_failed
    if _engine is None and not _engine_failed:
        try:
            from rapidocr_onnxruntime import RapidOCR

            _engine = RapidOCR()
            logger.info("RapidOCR 引擎加载成功")
        except Exception as exc:  # noqa: BLE001 - OCR 是增强能力，失败不阻断
            _engine_failed = True
            logger.warning("RapidOCR 不可用（%s），扫描页将无法识别", exc)

    if _engine is None:
        return ""

    try:
        # PyMuPDF pixmap.samples 为 RGB 通道原始字节，转 numpy 数组
        import numpy as np

        channels = len(pixmap_bytes) // (width * height)
        if channels < 3:
            return ""
        arr = np.frombuffer(pixmap_bytes, dtype=np.uint8)
        arr = arr[: width * height * channels].reshape((height, width, channels))
        arr = arr[:, :, :3]  # 只取 RGB 三通道

        result, _ = _engine(arr)
        if not result:
            return ""

        # RapidOCR 返回 [box, text, score] 列表；
        # 先按行分组（y 坐标接近的视为同一行），再按 x 排序拼接
        lines = _group_lines(result)
        return "\n".join(lines)
    except Exception as exc:  # noqa: BLE001 - 单页 OCR 失败返回空，不中断解析
        logger.warning("OCR 识别失败: %s", exc)
        return ""


def _group_lines(ocr_result: list) -> List[str]:
    """把 OCR 结果按行分组排序，返回文本行列表。"""
    # 提取 (y_center, x, text)
    entries: List[Tuple[float, float, str]] = []
    for item in ocr_result:
        box, text = item[0], item[1]
        if not text or not str(text).strip():
            continue
        try:
            ys = [p[1] for p in box]
            xs = [p[0] for p in box]
            entries.append((sum(ys) / len(ys), min(xs), str(text)))
        except (TypeError, IndexError, ValueError):
            continue

    if not entries:
        return []

    # 按 y 排序；y 坐标差小于平均行高一半的归为同一行
    entries.sort(key=lambda e: e[0])
    lines: List[Tuple[float, List[Tuple[float, str]]]] = []
    avg_height = 10.0
    for y, x, text in entries:
        if lines and abs(y - lines[-1][0]) < avg_height * 0.6:
            lines[-1][1].append((x, text))
            lines[-1] = (lines[-1][0], lines[-1][1])
        else:
            lines.append((y, [(x, text)]))

    result = []
    for _, row in lines:
        row.sort(key=lambda e: e[0])  # 行内按 x 排序
        result.append(" ".join(text for _, text in row))
    return result
