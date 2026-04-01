import concurrent.futures
import logging
import threading
from collections.abc import Sequence
from functools import partial
from typing import Any

from owslib.map.wms111 import WebMapService_1_1_1
from owslib.map.wms130 import WebMapService_1_3_0
from owslib.util import ResponseWrapper
from owslib.wms import WebMapService
from retrying import retry

logger = logging.getLogger(__name__)

MAX_RETRIES = 5
WAIT_MS = 0
TIMEOUT = 5

Bbox_T = list[float]


class WebMapServiceBulk:
    thread_local_storage = threading.local()

    def __init__(self, url: str, version: str, max_workers: int = 10, timeout: int = TIMEOUT) -> None:
        self.url = url
        self.version = version
        self.max_workers = max_workers
        self.timeout = timeout

    @property
    def wms(self) -> WebMapService_1_1_1 | WebMapService_1_3_0:
        if not hasattr(self.thread_local_storage, "wms"):
            wms = WebMapService(self.url, self.version, timeout=self.timeout)
            self.thread_local_storage.wms = wms
        return self.thread_local_storage.wms

    @retry(
        wait_fixed=WAIT_MS,
        stop_max_attempt_number=MAX_RETRIES,
        retry_on_exception=lambda exception: isinstance(exception, (ConnectionError,)),
    )  # TODO implement retry_call to use dynamic params https://pypi.org/project/retry/
    def _send_request(self, bbox, *args, **kwargs) -> ResponseWrapper:
        return self.wms.getmap(*args, bbox=bbox, **kwargs)

    def _get_single_map(self, bbox: Bbox_T, *args, **kwargs) -> dict[str, Any]:
        result = {"bbox": bbox}
        try:
            res = self._send_request(*args, bbox=bbox, **kwargs)
            url = res.geturl()
            logger.info(
                "(%s) Responded in (%s) sec from %s",
                res._response.status_code,
                res._response.elapsed.total_seconds(),
                url,
            )
            result["url"] = url
            res._response.raise_for_status()
            result["image"] = res.read()
        except Exception as e:
            result["error"] = str(e)
            logger.error("Exception occurred for bbox %s: %s", bbox, str(e))
        return result

    def getmaps(self, bboxes: Sequence[Bbox_T], *args, **kwargs):
        logger.info(
            "%d requests will be send with max connections = %d",
            len(bboxes),
            self.max_workers,
        )
        func = partial(self._get_single_map, *args, **kwargs)

        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            try:
                res = executor.map(func, bboxes)
            except Exception as e:
                logger.exception("Exception occured while getting maps: %s", e)
                raise
        return res
