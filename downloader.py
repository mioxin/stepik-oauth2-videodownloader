import argparse
import json
import os
import re
import sys
from typing import List, Dict, Optional

import requests
from requests.auth import HTTPBasicAuth
from requests import Session
# rich progress bar (single shared instance for all threads)
from rich.progress import (
    Progress,
    BarColumn,
    DownloadColumn,
    TextColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)
# console is used to hide cursor on older rich versions
from contextlib import contextmanager
@contextmanager
def cursor_hidden():
    # ANSI: hide cursor / show cursor
    try:
        sys.stdout.write("\x1b[?25l")
        sys.stdout.flush()
        yield
    finally:
        sys.stdout.write("\x1b[?25h")
        sys.stdout.flush()

# for threads
from concurrent.futures import ThreadPoolExecutor, as_completed

# Optional proxies; set via environment variable or uncomment below.
proxies = {
    'http': 'http://127.0.0.1:3129',
    'https': 'http://127.0.0.1:3129',
}

API_BASE = 'https://stepik.org/api'
# threads for concurrent downloads (tune to taste)
MAX_DOWNLOAD_THREADS = min(8, (os.cpu_count() or 2) * 2)


def sanitize_filename(name: str) -> str:
    """Remove characters that are illegal in filenames."""
    return re.sub(r'[:\"|/<>*?]+', '', name)


def get_json(session: Session, url: str, ids_list: List[int] = None) -> List[Dict]:
    """GET a URL (with optional query parameters) and return parsed JSON, raising on errors."""
    if ids_list is None:
        resp = session.get(url, headers=session.headers)
        resp.raise_for_status()
        return resp.json()

    results = []
    for params in ids_list:
        r = session.get(f'{url}/{params}', headers=session.headers)
        if r.status_code != 200:
            continue
        results.append(r.json())
    return results


def get_course_page(session: Session, course_id: str) -> dict:
    return get_json(session, f'{API_BASE}/courses/{course_id}')


def get_all_weeks(course_data: dict) -> List[int]:
    return course_data['courses'][0].get('sections', [])


def get_unit_list(session: Session, section_ids: List[int]) -> List[List[int]]:
    if not section_ids:
        return []
    # use repeated ids[] params per API requirement
    resp = get_json(session, f'{API_BASE}/sections', section_ids)
    session.section = [s['sections'][0]['title'] for s in resp]
    return [section['sections'][0]['units'] for section in resp]


def get_steps_list(session: Session, units_list: List[List[int]], week_index: int) -> List[int]:
    if week_index < 0 or week_index >= len(units_list):
        return []

    unit_ids = units_list[week_index]
    if not unit_ids:
        return []

    resp = get_json(session, f'{API_BASE}/units', unit_ids)
    lesson_ids = [u['units'][0]['lesson'] for u in resp]
    if not lesson_ids:
        return []

    resp = get_json(session, f'{API_BASE}/lessons', lesson_ids)
    steps = []
    for lesson in [u['lessons'][0] for u in resp]:
        steps.extend(lesson.get('steps', []))
    return steps


def get_only_video_steps(session: Session, step_ids: List[int]) -> List[Dict]:
    if not step_ids:
        return []

    resp = get_json(session, f'{API_BASE}/steps', step_ids)
    videos = []
    for step in [u['steps'][0] for u in resp]:
        block = step.get('block', {})
        video = block.get('video')
        if video:
            videos.append(block)
    print('Only video:', len(videos))
    return videos


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Stepik downloader')
    parser.add_argument('-c', '--client_id', required=True,
                        help='your client_id from https://stepik.org/oauth2/applications/')
    parser.add_argument('-s', '--client_secret', required=True,
                        help='your client_secret from https://stepik.org/oauth2/applications/')
    parser.add_argument('-i', '--course_id', required=True, help='course id')
    parser.add_argument('-w', '--week_id', type=int, default=None,
                        help='week number starting from 1 (downloads full course if omitted)')
    parser.add_argument('-q', '--quality', choices=['360', '720', '1080'], default='720',
                        help='quality of a video. Default is 720')
    parser.add_argument('-o', '--output_dir', default='.',
                        help='output directory. Default is current folder')
    return parser.parse_args()


def download_file(
    session: Session,
    url: str,
    dest: str,
    retries: int = 3,
    progress: Optional[Progress] = None,
    task_id: Optional[int] = None,
) -> None:
    """Download a URL to destination using streaming with retries.
    If ``progress``/``task_id`` are supplied, the given task is updated
    instead of creating a new display.
    """
    attempt = 0
    while attempt < retries:
        try:
            with session.get(url, stream=True, timeout=30) as r:
                r.raise_for_status()
                total = int(r.headers.get('content-length', 0))
                if progress is not None and task_id is not None:
                    progress.update(task_id, total=total)
                with open(dest, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            if progress is not None and task_id is not None:
                                progress.update(task_id, advance=len(chunk))
            return
        except (requests.exceptions.RequestException, IOError) as exc:
            attempt += 1
            if os.path.exists(dest):
                os.remove(dest)
            if attempt < retries:
                print(f"download failed ({exc}), retry {attempt}/{retries}...")
                continue
            else:
                raise


def download_worker(
    session: Session,
    url: str,
    dest: str,
    progress: Optional[Progress] = None,
    task_id: Optional[int] = None,
) -> None:
    """Thread target; skip if file already present."""
    if os.path.isfile(dest):
        return
    download_file(session, url, dest, progress=progress, task_id=task_id)


def make_session_with_retries(retries: int = 3, backoff: float = 0.5) -> Session:
    """Create a ``requests.Session`` configured with retry logic."""
    session = requests.Session()
    adapter = requests.adapters.HTTPAdapter(
        max_retries=requests.adapters.Retry(
            total=retries,
            backoff_factor=backoff,
            status_forcelist=[429, 500, 502, 503, 504],
            raise_on_status=False,
        )
    )
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    return session


def main():
    args = parse_arguments()
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    session = make_session_with_retries(retries=5, backoff=0.5)
    session.proxies.update(proxies)
    session.verify = False

    auth = HTTPBasicAuth(args.client_id, args.client_secret)
    token_resp = session.post(f'https://stepik.org/oauth2/token/',
                              data={'grant_type': 'client_credentials'},
                              auth=auth)
    token_resp.raise_for_status()
    token = token_resp.json().get('access_token')
    if not token:
        print('Failed to obtain access token')
        sys.exit(1)
    session.headers.update({'Authorization': f'Bearer {token}'})

    course_data = get_course_page(session, args.course_id)
    course_name = sanitize_filename(course_data['courses'][0].get('title', args.course_id)).strip()

    weeks = get_all_weeks(course_data)
    units = get_unit_list(session, weeks)
    print('Units found:', units)

    base_dir = os.path.join(args.output_dir, course_name)
    os.makedirs(base_dir, exist_ok=True)

    for week_idx in range(len(weeks)):
        if args.week_id is not None and week_idx + 1 != args.week_id:
            continue

        steps = get_steps_list(session, units, week_idx)
        print(f'Week {week_idx+1}: steps found:', steps)

        videos = get_only_video_steps(session, steps)
        if not videos:
            continue

        week_dir = os.path.join(base_dir, f'week_{week_idx+1}')
        os.makedirs(week_dir, exist_ok=True)
        inp_path = os.path.join(week_dir, 'inp.txt')

        # build task list and write concat file
        tasks: List[tuple] = []
        with open(inp_path, 'w', encoding='utf-8') as inp:
            for i, video in enumerate(videos):
                urls = video['video'].get('urls', [])
                chosen = next((u for u in urls if u.get('quality') == args.quality), None)
                if chosen is None:
                    chosen = urls[0]
                    print(f"Requested quality {args.quality} not available; using {chosen.get('quality')}")
                url = chosen['url']
                filename = os.path.join(week_dir, f'Video_{i}.mp4')
                inp.write(f"file 'Video_{i}.mp4'\n")
                tasks.append((url, filename))

        # download in parallel with a shared rich.Progress display
        if tasks:
            print(f"Downloading {len(tasks)} files using {MAX_DOWNLOAD_THREADS} threads")
            with cursor_hidden():
                with Progress(
                    TextColumn("[bold blue]{task.fields[filename]}", justify="right"),
                    TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                    BarColumn(),
                    DownloadColumn(),
                    TransferSpeedColumn(),
                    TimeRemainingColumn(),
                ) as progress:
                    with ThreadPoolExecutor(max_workers=MAX_DOWNLOAD_THREADS) as executor:
                        future_map = {}
                        for url, fname in tasks:
                            if os.path.isfile(fname):
                                continue
                            tid = progress.add_task("", filename=os.path.basename(fname), total=0)
                            fut = executor.submit(download_worker, session, url, fname, progress, tid)
                            future_map[fut] = fname
                        for fut in as_completed(future_map):
                            fname = future_map[fut]
                            try:
                                fut.result()
                            except Exception as exc:
                                print(f"Error while downloading {fname}: {exc}")

        print('All steps downloaded for week', week_idx+1)

        # concat
        outputfilename = (
            os.path.join(args.output_dir, course_name, str(week_idx+1) + '. '
                         + sanitize_filename(session.section[week_idx])).rstrip() + '.mp4'
        )
        if not os.path.isfile(outputfilename):
            print("Start concat by FFMPEG... " + outputfilename)
            cmd = f'start /MIN ffmpeg -f concat -safe 0 -i "{inp_path}" -c copy "{outputfilename}"'
            err = os.system(cmd)
            if err > 0:
                print('Concatenation failed.')
        else:
            print('Concat file ' + outputfilename + ' exist.')


if __name__ == "__main__":
    main()