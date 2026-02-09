import argparse
import json
import os
import urllib
import urllib.request
import requests
from http_ntlm import HTTP_win
import sys
import re
from requests.auth import HTTPBasicAuth

class Utils:
    def parse_arguments():
        """
        Parse input arguments with help of argparse.
        """
        parser = argparse.ArgumentParser(
            description='Stepik downloader')

        parser.add_argument('-c', '--client_id',
                            help='your client_id from https://stepik.org/oauth2/applications/',
                            required=True)

        parser.add_argument('-s', '--client_secret',
                            help='your client_secret from https://stepik.org/oauth2/applications/',
                            required=True)

        parser.add_argument('-i', '--course_id',
                            help='course id',
                            required=True)

        parser.add_argument('-w', '--week_id',
                            help='week id starts from 1 (if not set then it will download the whole course)',
                            type=int,
                            default=None)

        parser.add_argument('-q', '--quality',
                            help='quality of a video. Default is 720',
                            choices=['360', '720', '1080'],
                            default='720')

        parser.add_argument('-p', '--proxy',
                            help='your proxy server',
                            default=None)

        parser.add_argument('-o', '--output_dir',
                            help='output directory. Default is the current folder',
                            default='.')

        args = parser.parse_args()

        return args

    def reporthook(blocknum, blocksize, totalsize): # progressbar
        readsofar = blocknum * blocksize
        if totalsize > 0:
            percent = readsofar * 1e2 / totalsize
            s = "\r{0:5.1f}%% {2:{1},.0f}Kb / {3:,.0f}Kb".format(percent, len(str(totalsize)), readsofar/1024, totalsize/1024)
            sys.stderr.write(s)
            if readsofar >= totalsize: # near the end
                sys.stderr.write("\n")
        else: # total size is unknown
            sys.stderr.write("read %d\n" % (readsofar,))


class Downloader:
    proxyDict = None
    sections = []
    exclude_simbols = r'[:"|/<>*?]?'
    #a = None
    
    def __init__(self, args):
        self.a = args
        #auth = HTTPBasicAuth(args.client_id, args.client_secret)
        self.reqst = HTTP_win()
        headers={
            'Content-Type': 'application/x-www-form-urlencoded',
            'Authorization': 'Basic ZGxKN2xWWDRHMVRSZkpoR000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000uZTkxMHFGMjhwMUc2UFVpb2VsM1d4eUVtYkF1d09vaWVmdWdheEtuRkNRc2ZTMlVROQ=='
        }
        resp_text = self.reqst.get_text(self.reqst.url_post)('https://stepik.org/oauth2/token/', 'grant_type=client_credentials',args.client_id, args.client_secret,headers)
        print(resp_text)
        self.token = json.loads(resp_text)['access_token']
        self.course_data = self.get_course_page('http://stepik.org/api/courses/' + args.course_id)
        
    def get_course_page(self, api_url):
        return json.loads(self.reqst.get_text(self.reqst.url_get)(api_url, headers={'Authorization': 'Bearer ' + self.token}))
        #return json.loads(requests.get(api_url, headers={'Authorization': 'Bearer ' + self.token}, proxies=self.proxyDict).text)


    def get_all_weeks(self, stepik_resp):
        return stepik_resp['courses'][0]['sections']


    def get_unit_list(self, section_list):
        global sections
        l_resp = [json.loads(self.reqst.get_text(self.reqst.url_get)('https://stepik.org/api/sections/' + str(arr),
                            headers={'Authorization': 'Bearer ' + self.token})) for arr in section_list]
        sections = [title['sections'][0]['title'] for title in l_resp]
        return [section['sections'][0]['units'] for section in l_resp]


    def get_steps_list(self, units_list, week):
        data = [json.loads(self.reqst.get_text(self.reqst.url_get)('https://stepik.org/api/units/' + str(unit_id),
                            headers={'Authorization': 'Bearer ' + self.token})) for unit_id in units_list[week - 1]]
        lesson_lists = [elem['units'][0]['lesson'] for elem in data]
        #temp = self.reqst.get_text(self.reqst.url_get)('https://stepik.org/api/lessons/' + str(lesson_id),headers={'Authorization': 'Bearer ' + self.token})['lessons']
        data = [json.loads(self.reqst.get_text(self.reqst.url_get)('https://stepik.org/api/lessons/' + str(lesson_id),
                            headers={'Authorization': 'Bearer ' + self.token}))['lessons'][0] for lesson_id in lesson_lists]
        
        return data #[item for sublist in data for item in sublist]


    def get_only_video_steps(self, step_list):
        resp_list = list()
        for les in step_list:
            lesson_name = les['title']
            for s in les['steps']:
                
                resp = json.loads(self.reqst.get_text(self.reqst.url_get)('https://stepik.org/api/steps/' + str(s),
                                               headers={'Authorization': 'Bearer ' + self.token}))
                if resp['steps'][0]['block']['video']:
                    resp['steps'][0]['block']['lesson_name'] = lesson_name
                    resp['steps'][0]['block']['step_id'] = s
                    resp_list.append(resp['steps'][0]['block'])
                    
        print('Only video:', len(resp_list))
        return resp_list

    def run(self):
        course_name = re.sub(self.exclude_simbols,'', self.course_data['courses'][0]['title'])
        print("Course name: " + course_name)
        
        weeks_num = self.get_all_weeks(self.course_data)
        print("Number of weeks: " + str(len(weeks_num)))

        all_units = self.get_unit_list(weeks_num)
        print("Number of units: " + str(len(all_units)))
        # Loop through all week in a course and
        # download all videos or
        # download only for the week_id is passed as an argument.
        for week in range(1, len(weeks_num)+1):
            #file_num = 0
            # Skip if week_id is passed as an argument
            args_week_id = str(self.a.week_id)
            if args_week_id != "None":
                # week_id starts from 1 and week counts from 0!
                if week != int(args_week_id):
                    continue

            all_steps = self.get_steps_list(all_units, week)
            only_video_steps = self.get_only_video_steps(all_steps)

            url_list_with_q = []
            les_name = ''
            step_num = 0

            # Loop through videos and store the url link and the quality.
            for video_step in only_video_steps:            
                step_num = step_num + 1
                
                les_name = (str(step_num).zfill(len(str(len(only_video_steps))))
                    + '. ' + re.sub(self.exclude_simbols,'', video_step['lesson_name']).rstrip()
                    + '.mp4')
                
                video_link = None
                msg = None

                # Check a video quality.
                for url in video_step['video']['urls']:
                    if url['quality'] == self.a.quality:
                        video_link = url['url']

                # If the is no required video quality then download
                # with the best available quality.
                if video_link is None:
                    msg = "The requested quality = {} is not available!".format(self.a.quality)
                    video_link = video_step['video']['urls'][0]['url']

                # Store link and quality.
                url_list_with_q.append({'url': video_link, 'msg': msg, 'name': les_name, 'id': video_step['step_id']})

            # Compose a folder name.
            folder_name = (os.path.join(self.a.output_dir, course_name, str(week) + '. '
                                       + re.sub(self.exclude_simbols,'', sections[week-1])).rstrip())

            # Create a folder if needed.
            if not os.path.isdir(folder_name):
                try:
                    # Create a directory for a particular week in the course.
                    os.makedirs(folder_name)
                except PermissionError:
                    print("Run the script from admin")
                    exit(1)
                except FileExistsError:
                    print("Please delete the folder " + folder_name)
                    exit(1)

            inputfilename = os.path.join(folder_name, 'inp.txt')
            inputfile = open(inputfilename,'w')
            for el in url_list_with_q:
                # Print a message if something wrong.
                if el['msg']:
                    print("{}".format(el['msg']))

                filename = os.path.join(folder_name, el['name'])
                inputfile.write('file \''+filename+'\'\n')
                if not os.path.isfile(filename):
                    try:
                        print('Downloading file ', filename)
                        print('URL ', el['url'])
                        #urllib.request.urlretrieve(el['url'], filename, Utils.reporthook)
                        if not os.path.isfile(filename):
                            err = os.system(f'curl -U : -k -x proxy.org:8080 --proxy-ntlm -o "{filename}" {el["url"]}')
                            if err > 0 :
                                print('Downloading failed.')
                        else:
                            print('Download '+filename+' exist.')
                    except urllib.error.ContentTooShortError:
                        os.remove(filename)
                        print('Error while downloading. File {} deleted:'.format(filename))
                    except KeyboardInterrupt:
                        if os.path.isfile(filename):
                            os.remove(filename)
                        print('\nAborted')
                        exit(1)
                else:
                    print('File {} already exist'.format(filename))
            print("All steps downloaded")
            inputfile.close()
            #concat videofiles by ffmpeg 
            outputfilename = (os.path.join(self.a.output_dir, course_name, str(week) + '. '
                                       + re.sub(self.exclude_simbols,'', sections[week-1])).rstrip()+'.mp4')
            if not os.path.isfile(outputfilename):
                err = os.system('start /MIN ffmpeg -f concat -safe 0 -i "'+inputfilename +'" -c copy "'+outputfilename+'"')
                if err > 0 :
                    print('Concatenation failed.')
            else:
                print('Concat file '+outputfilename+' exist.')

class DownloaderProxy(Downloader):
    def __init__(self, a):
        self.proxyDict = {"http": a.proxy, "https": a.proxy}
        Downloader.__init__(self, a)
        
    def p(self): print(self.a)


if __name__ == "__main__":
    arguments = Utils.parse_arguments()
    d = DownloaderProxy(arguments)
    d.run()
    #d.p()
