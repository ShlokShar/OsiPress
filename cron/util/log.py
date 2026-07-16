
import json
from datetime import (
    datetime,
    timedelta,
    timezone
)
from pathlib import Path

LOG_PATH = Path(__file__).resolve().parent.parent / "log.json"


def add_log(message: str) -> None:
    """
    Adds a message with a timestamp to the log.json file.
    Used primarily to document exceptions during the cron job.

    :param message: the message that describes the exception
    :return: None
    """

    try:
        if LOG_PATH.exists():
            with LOG_PATH.open("r", encoding="utf-8") as file:
                data = json.load(file)
        else:
            data = {"logs": []}

        logs = data["logs"]
        utc_now = datetime.now(timezone.utc)
        week_ago = (utc_now - timedelta(days=7)).timestamp()

        data["logs"] = [
            log for log in logs
            if isinstance(log, dict)
            and isinstance(log.get("timestamp"), (int, float))
            and log["timestamp"] >= week_ago
        ]
        data["logs"].append(
            {
                "timestamp": utc_now.timestamp(),
                "message": message,
            }
        )

        temporary_path = LOG_PATH.with_suffix(".tmp")
        with temporary_path.open("w", encoding="utf-8") as file:
            json.dump(data, file, indent=2, ensure_ascii=False)
        temporary_path.replace(LOG_PATH)
    except Exception as exception:
        print(f"Failed to write log: {exception}")
