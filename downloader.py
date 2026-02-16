import argparse
import json
import os
import re
import sys
from typing import List, Dict, Optional

import requests
from requests.auth import HTTPBasicAuth
from requests import Session

# Optional proxies; set via environment variable or uncomment below.
proxies = {
    'http': 'http://127.0.0.1:3129',
    'https': 'http://127.0.0.1:3129',
}

API_BASE = 'https://stepik.org/api'


def sanitize_filename(name: str) -> str:
    """Remove characters that are illegal in filenames."""
    return re.sub(r'[:\"|/<>*?]+', '', name)


def get_json(session: Session, url: str) -> dict:
    """GET a URL and return parsed JSON, raising on errors."""
    resp = session.get(url, headers=session.headers)
    resp.raise_for_status()
    return resp.json()


def get_course_page(session: Session, course_id: str) -> dict:
    return get_json(session, f'{API_BASE}/courses/{course_id}')


def get_all_weeks(course_data: dict) -> List[int]:
    return course_data['courses'][0].get('sections', [])


def get_unit_list(session: Session, section_ids: List[int]) -> List[List[int]]:
    if not section_ids:
        return []
    
    ids_str = ','.join(str(i) for i in section_ids)
    resp = get_json(session, f'{API_BASE}/sections?ids={ids_str}')
    sections = resp.get('sections', [])
    
    # store titles in session for later use
    session.sections = [s.get('title', '') for s in sections]

    return [s.get('units', []) for s in sections]


def get_steps_list(session: Session, units_list: List[List[int]], week_index: int) -> List[int]:
    if week_index < 0 or week_index >= len(units_list):
        return []
    
    unit_ids = units_list[week_index]

    if not unit_ids:
        return []
    
    ids_str = ','.join(str(uid) for uid in unit_ids)
    resp = get_json(session, f'{API_BASE}/units?ids={ids_str}')
    lesson_ids = [u['lesson'] for u in resp.get('units', [])]

    if not lesson_ids:
        return []
    
    ids_str = ','.join(str(lid) for lid in lesson_ids)
    resp = get_json(session, f'{API_BASE}/lessons?ids={ids_str}')
    steps = []

    for lesson in resp.get('lessons', []):
        steps.extend(lesson.get('steps', []))

    return steps


def get_only_video_steps(session: Session, step_ids: List[int]) -> List[Dict]:
    if not step_ids:
        return []
    
    ids_str = ','.join(str(sid) for sid in step_ids)
    resp = get_json(session, f'{API_BASE}/steps?ids={ids_str}')
    videos = []

    for step in resp.get('steps', []):
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


def download_file(session: Session, url: str, dest: str) -> None:
    """Download a URL to destination using streaming."""
    with session.get(url, stream=True) as r:
        r.raise_for_status()
        total = int(r.headers.get('content-length', 0))
        with open(dest, 'wb') as f:
            downloaded = 0
            for chunk in r.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total:
                        percent = downloaded * 100 / total
                        sys.stderr.write(f'\r{percent:5.1f}% {downloaded} / {total}')
            if total:
                sys.stderr.write('\n')


def main():
    args = parse_arguments()

    # prepare session
    session = requests.Session()
    session.proxies.update(proxies)
    session.verify = False  # consider removing in production

    auth = HTTPBasicAuth(args.client_id, args.client_secret)
    token_resp = session.post(f'{API_BASE}/oauth2/token/',
                              data={'grant_type': 'client_credentials'},
                              auth=auth)
    
    token_resp.raise_for_status()
    token = token_resp.json().get('access_token')

    if not token:
        print('Failed to obtain access token')
        sys.exit(1)
    
    session.headers.update({'Authorization': f'Bearer {token}'})

    course_data = get_course_page(session, args.course_id)
    course_name = sanitize_filename(course_data['courses'][0].get('title', args.course_id))

    weeks = get_all_weeks(course_data)
    units = get_unit_list(session, weeks)

    base_dir = os.path.join(args.output_dir, course_name)
    os.makedirs(base_dir, exist_ok=True)

    for week_idx in range(len(weeks)):

        if args.week_id is not None and week_idx + 1 != args.week_id:
            continue

        steps = get_steps_list(session, units, week_idx)
        videos = get_only_video_steps(session, steps)

        if not videos:
            continue

        week_dir = os.path.join(base_dir, f'week_{week_idx+1}')
        os.makedirs(week_dir, exist_ok=True)
        inp_path = os.path.join(week_dir, 'inp.txt')

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

                if not os.path.isfile(filename):
                    print('Downloading file', filename)
                    try:
                        download_file(session, url, filename)
                    except Exception as exc:
                        if os.path.exists(filename):
                            os.remove(filename)
                        print(f'Error while downloading {filename}: {exc}')

        print('All steps downloaded for week', week_idx+1)

        section_title = getattr(session, 'sections', [None])[week_idx] or ''
        outputfilename = os.path.join(base_dir, f"{week_idx+1}. {sanitize_filename(section_title)}.mp4")
        
        if not os.path.isfile(outputfilename):
            print("Start concat by FFMPEG... " + outputfilename)
            import subprocess
            res = subprocess.run(['ffmpeg', '-f', 'concat', '-safe', '0', '-i', inp_path,
                                  '-c', 'copy', outputfilename])
            if res.returncode != 0:
                print('Concatenation failed.')
        else:
            print('Concat file', outputfilename, 'exists.')


if __name__ == "__main__":
    main()
