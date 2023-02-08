# Stepic.org Video Downloader

Example of OAuth2 application for Stepic.org. 

Downloads all video files from a module (week) of a course or the whole course.

1. Go to https://stepik.org/oauth2/applications/

2. Register your application with settings:  
`Client type: confidential`  
`Authorization Grant Type: client-credentials`

3. Install requests module

  ```
  pip install requests
  ```

4. Run the script

  ```
 python3 downloader.py [-h] --course_id=COURSE_ID --client_id=CLIENT_ID --client_secret=CLIENT_SECRET [--week_id=WEEK_ID] [--quality=360|720|1080] [--output_dir=.]
  ```
Additions
===
Added new loader downloader_stepic_ntlm_curl.py.
It need for working across a corporate ntlm web proxy.
The Script use curl.exe for download a videos and ffmpeg.exe for merging step's video in the general video of week.

Also it renew the output format.

![screen](./screen.png)
