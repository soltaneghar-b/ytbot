#!/usr/bin/env python3
"""
YouTube converter → metadata.txt
Reads environment variables for configuration.
"""

import os, sys, json, time, re
import requests

YT_URL = os.environ['YT_URL']
OUTPUT_TYPE = os.environ['OUTPUT_TYPE']
QUALITY = os.environ.get('QUALITY', '720p')
API_ENDPOINT = os.environ['API_ENDPOINT']
REFERER = os.environ['REFERER_URL']
USER_AGENT = os.environ['USER_AGENT']

STATUS_CHECK_INTERVAL = 2
MAX_ATTEMPTS = 150
RETRY_MAX = 3
CONVERSION_RETRIES = 3

VIDEO_QUALITIES = ['144p', '360p', '480p', '720p', '1080p']
AUDIO_BITRATES = ['64k', '128k', '192k', '320k']


def safe_json(resp):
    try:
        return resp.json()
    except Exception:
        print(f"❌ Non-JSON response (HTTP {resp.status_code}): {resp.text[:300]}")
        sys.exit(1)


def retryable_request(method, url, session, **kwargs):
    last_exc = None
    for i in range(RETRY_MAX):
        try:
            resp = session.request(method, url, timeout=30, **kwargs)
            if resp.status_code < 500 and resp.status_code != 429:
                return resp
            print(f"⚠️ Retryable status {resp.status_code} – attempt {i+1}/{RETRY_MAX}")
        except requests.RequestException as e:
            last_exc = e
            print(f"⚠️ Request error, retry {i+1}/{RETRY_MAX}: {e}")
        time.sleep((2 ** i) * 1.5)
    if last_exc:
        raise last_exc
    return resp


def normalize_quality(output_type, quality_input):
    try:
        quality = quality_input.lower().strip()
        quality_map = {'4k':'1080p','2k':'1080p','2160p':'1080p','1440p':'1080p','240p':'360p'}
        if output_type == 'audio':
            if quality.endswith('bps'):
                quality = quality[:-3]
            if not quality.endswith('k'):
                quality += 'k'
            if quality in AUDIO_BITRATES:
                return quality
            try:
                num = int(''.join(filter(str.isdigit, quality)))
                best = min(AUDIO_BITRATES, key=lambda b: abs(int(b[:-1]) - num))
            except:
                best = '192k'
            print(f"🔄 Audio fallback from '{quality_input}' → {best}")
            return best
        else:  # video
            if quality in quality_map:
                return quality_map[quality]
            quality = quality.replace('k', '')
            if not quality.endswith('p'):
                quality += 'p'
            if quality in VIDEO_QUALITIES:
                return quality
            if quality in quality_map:
                return quality_map[quality]
            print(f"🔄 Video fallback from '{quality_input}' → 720p")
            return '720p'
    except Exception:
        return '720p' if output_type == 'video' else '192k'


if OUTPUT_TYPE not in ('video', 'audio'):
    print(f"⚠️ Unknown type '{OUTPUT_TYPE}', forcing to video")
    OUTPUT_TYPE = 'video'

QUALITY = normalize_quality(OUTPUT_TYPE, QUALITY)

print(f"🎯 Target: {OUTPUT_TYPE.upper()} @ {QUALITY}")
print("="*50)

HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "application/json",
    "Referer": REFERER,
    "Content-Type": "application/json",
    "Origin": REFERER,
}

session = requests.Session()

try:
    session.get(REFERER, headers=HEADERS, timeout=15)
except requests.RequestException as e:
    print(f"❌ Preflight failed: {e}")
    sys.exit(1)


# ---------- retry wrapper for the whole conversion ----------
def attempt_conversion():
    payload = {
        "url": YT_URL,
        "os": "linux",
        "output": {
            "type": OUTPUT_TYPE,
            "format": "mp3" if OUTPUT_TYPE == 'audio' else "mp4",
        }
    }
    if OUTPUT_TYPE == 'audio':
        payload["audio"] = {"bitrate": QUALITY}
    else:
        payload["output"]["quality"] = QUALITY

    print(f"📤 Requesting conversion...")
    print(f"📋 Payload: {json.dumps(payload, indent=2)}")

    try:
        response = retryable_request("POST", API_ENDPOINT, session, json=payload, headers=HEADERS)
        if response.status_code != 200:
            print(f"❌ API error ({response.status_code}): {response.text[:300]}")
            if response.status_code == 400:
                if OUTPUT_TYPE == 'audio':
                    payload["audio"]["bitrate"] = "192k"
                else:
                    payload["output"]["quality"] = "720p"
                response = session.post(API_ENDPOINT, json=payload, headers=HEADERS, timeout=30)
                if response.status_code != 200:
                    print(f"❌ Fallback also failed ({response.status_code})")
                    return None, None, None, None
            elif response.status_code == 500:
                # Check for non-retryable error: "Failed to fetch video metadata"
                try:
                    error_data = response.json()
                    error_msg = error_data.get('error', {}).get('message', '')
                    if 'Failed to fetch video metadata' in error_msg:
                        print("⛔ Video metadata unavailable (geo-restricted / private / age-limited).")
                        return None, None, None, "METADATA_FAIL"
                except Exception:
                    pass
                return None, None, None, None
            else:
                return None, None, None, None
        data = safe_json(response)
    except requests.RequestException as e:
        print(f"❌ Request failed: {e}")
        return None, None, None, None

    status_url = data.get('statusUrl')
    title = data.get('title', 'youtube_video')
    if not status_url:
        print("❌ No statusUrl in response")
        print(json.dumps(data, indent=2))
        return None, None, None, None

    print(f"✅ Registered: {title}")
    print("="*50)

    download_url = None
    last_progress = -1
    stall_count = 0
    attempt = 0
    max_attempts = MAX_ATTEMPTS
    subtitle_url = None

    while attempt < max_attempts:
        attempt += 1
        time.sleep(STATUS_CHECK_INTERVAL)
        print(f"🔄 Status [{attempt}/{max_attempts}]...", end=' ')
        try:
            status_resp = session.get(status_url, headers=HEADERS, timeout=15)
            status_data = safe_json(status_resp)
        except requests.RequestException as e:
            print(f"⚠️ check failed: {e}")
            continue

        status = status_data.get('status')
        progress = status_data.get('progress', 0)
        print(f"{status} | {progress}%")

        if not subtitle_url and status_data.get('subtitles'):
            subtitle_url = status_data['subtitles']
            print("📝 Subtitle URL found")

        if status == 'completed':
            download_url = status_data.get('downloadUrl')
            if download_url:
                print("🎉 Completed successfully!")
                if status_data.get('subtitles'):
                    subtitle_url = status_data['subtitles']
            else:
                print("❌ Completed but no downloadUrl – aborting conversion attempt")
            break
        elif status in ('failed', 'error'):
            print(f"❌ Conversion {status}: " + json.dumps(status_data.get('error', {})))
            download_url = None
            break
        elif status not in ('pending', 'processing'):
            print(f"❌ Unexpected status '{status}' – aborting conversion attempt")
            print(json.dumps(status_data, indent=2))
            download_url = None
            break

        if progress > last_progress:
            last_progress = progress
            stall_count = 0
            if attempt >= max_attempts - 5 and max_attempts < 300:
                max_attempts += 30
                print(f"   ↳ Progress still climbing, extended limit to {max_attempts}")
        elif progress < 100:
            stall_count += 1
            if stall_count >= 10:
                print("⏰ Progress stalled for 10 checks – aborting conversion attempt")
                download_url = None
                break

    return download_url, subtitle_url, title, status_url


# ---------- outer retry loop ----------
final_download_url = None
final_subtitle_url = None
final_title = ""
final_status_url = ""
permanent_fail = False

for retry_attempt in range(1, CONVERSION_RETRIES + 1):
    print(f"\n🔄 Conversion attempt {retry_attempt}/{CONVERSION_RETRIES}")
    download_url, subtitle_url, title, status_url = attempt_conversion()
    if download_url:
        final_download_url = download_url
        final_subtitle_url = subtitle_url
        final_title = title
        final_status_url = status_url
        break
    else:
        # Special marker for permanent metadata failure
        if status_url == "METADATA_FAIL":
            print("⛔ Permanent metadata failure – not retrying further.")
            permanent_fail = True
            break
        if retry_attempt < CONVERSION_RETRIES:
            wait = 10 * retry_attempt  # exponential backoff: 10, 20, 30 seconds
            print(f"🔁 Conversion failed, retrying in {wait} seconds...")
            time.sleep(wait)
        else:
            print("❌ All conversion attempts exhausted.")
            sys.exit(1)

if permanent_fail:
    # Output a user-friendly message that the bot can relay (optional)
    print("USER_ERROR: ویدیو در دسترس نیست (محدودیت جغرافیایی یا سنی). لطفاً ویدیوی دیگری امتحان کنید.")
    sys.exit(1)

if not final_download_url:
    print("❌ Conversion did not produce a download URL after retries.")
    sys.exit(1)

# Generate filename
video_id_match = re.search(r'(?:v=|\/)([a-zA-Z0-9_-]{11})', YT_URL)
video_id = video_id_match.group(1) if video_id_match else "unknown"
safe_title = re.sub(r'[^a-zA-Z0-9\-_]', '_', final_title.replace(' ', '_'))[:60].strip('_') or video_id
timestamp = time.strftime("%Y%m%d-%H%M%S")
ext = "mp3" if OUTPUT_TYPE == 'audio' else "mp4"
quality_label = QUALITY
filename = f"{safe_title}_{video_id}_{quality_label}_{timestamp}.{ext}"

with open('/tmp/metadata.txt', 'w', encoding='utf-8') as f:
    f.write(f"{final_download_url}\n{filename}\n{OUTPUT_TYPE}\n{QUALITY}\n{final_status_url}\n")
    if final_subtitle_url:
        f.write(f"{final_subtitle_url}\n")
    else:
        f.write("NONE\n")

print(f"📥 Download URL: {final_download_url[:80]}...")
print(f"📄 Filename: {filename}")
if final_subtitle_url:
    print(f"📝 Subtitle URL: {final_subtitle_url}")
else:
    print("📝 No subtitles available")
