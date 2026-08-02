"""
ffmpeg_utils.py — เรียก ffmpeg ผ่าน subprocess สำหรับ extract/ตัดไฟล์เสียง

ตามการตัดสินใจ Module 2: รองรับไฟล์เสียง/วิดีโอ 3 แหล่ง (Google Meet, MS Teams, เครื่องบันทึก/
มือถือ) แบบ manual upload — ใช้ ffmpeg รองรับทุกฟอร์แมตที่รู้จักโดยไม่จำกัดชนิดไฟล์ล่วงหน้า (ไม่เช็ค
นามสกุลไฟล์ในโค้ดนี้ ปล่อยให้ ffmpeg เป็นคนตัดสินว่าเปิดได้หรือไม่)

ต้องมี ffmpeg อยู่ใน PATH ของเครื่อง — ไม่ได้ bundle มาด้วย (ยังไม่ verify ว่าผู้ใช้ติดตั้งแล้วหรือยัง
ดู task.md Module 2 checklist "ติดตั้งและปรับใช้ ffmpeg")
"""
import subprocess


class FFmpegError(Exception):
    """ffmpeg คืนค่า non-zero exit code หรือหาไฟล์ ffmpeg ไม่เจอ"""


def _run_ffmpeg(args: list[str]) -> None:
    try:
        result = subprocess.run(
            ["ffmpeg", "-y", *args],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as e:
        raise FFmpegError(
            "ไม่พบ ffmpeg ใน PATH — ติดตั้งก่อน (ดู task.md Module 2 checklist)"
        ) from e

    if result.returncode != 0:
        # ffmpeg พิมพ์รายละเอียด error ไปที่ stderr เสมอ — ตัดมาแค่บรรทัดท้ายๆ กันข้อความยาวเกินไป
        tail = "\n".join(result.stderr.strip().splitlines()[-15:])
        raise FFmpegError(f"ffmpeg exit code {result.returncode}:\n{tail}")


def extract_mono_16k_wav(input_path: str, output_path: str) -> None:
    """แปลงไฟล์เสียง/วิดีโอต้นฉบับ (ฟอร์แมตอะไรก็ได้ที่ ffmpeg เปิดได้) เป็น 16kHz mono WAV —
    ฟอร์แมตที่ทั้ง typhoon-asr และ Diarization_ThaiSpeech_2022 ต้องการ"""
    _run_ffmpeg([
        "-i", input_path,
        "-ar", "16000",
        "-ac", "1",
        "-vn",  # ตัด video stream ทิ้ง เผื่อ input เป็นไฟล์วิดีโอ (Google Meet/Teams recording)
        output_path,
    ])


def get_duration_seconds(input_path: str) -> float:
    """เรียก ffprobe หาความยาวไฟล์ (วินาที) — ใช้คำนวณจำนวนชิ้นตอนตัด ASR เป็นชิ้นละ 1 ชม."""
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                input_path,
            ],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as e:
        raise FFmpegError(
            "ไม่พบ ffprobe ใน PATH — มากับ ffmpeg ปกติ เช็คการติดตั้งอีกที"
        ) from e

    if result.returncode != 0 or not result.stdout.strip():
        raise FFmpegError(f"ffprobe อ่านความยาวไฟล์ไม่ได้: {result.stderr.strip()}")

    return float(result.stdout.strip())


def extract_chunk(input_wav_path: str, output_path: str, start_seconds: float, duration_seconds: float) -> None:
    """ตัดไฟล์ WAV (16kHz mono ที่ extract ไว้แล้ว) เป็นชิ้นตามช่วงเวลาที่กำหนด — ใช้ -c copy
    เพราะ input เป็น WAV PCM อยู่แล้ว ไม่ต้อง re-encode ซ้ำ (เร็วกว่า ไม่เสียคุณภาพเพิ่ม)"""
    _run_ffmpeg([
        "-i", input_wav_path,
        "-ss", str(start_seconds),
        "-t", str(duration_seconds),
        "-c", "copy",
        output_path,
    ])
