import win32com.client
from functools import wraps

url = 'https://www-int.hq.bc/?'

try:
    import _winreg as winreg
except:
    import winreg

class HTTP_win:
    proxy = ""
    proxyExclude = ""
    isProxy = False
    httpCOM = win32com.client.Dispatch('Msxml2.ServerXMLHTTP.6.0')

    def __init__(self):
        self.get_proxy()
        if self.isProxy:
            self.httpCOM.setProxy(2, self.proxy, self.proxyExclude)


    def get_proxy(self):
        oReg = winreg.ConnectRegistry(None, winreg.HKEY_CURRENT_USER)
        oKey = winreg.OpenKey(oReg, r'Software\Microsoft\Windows\CurrentVersion\Internet Settings')
        dwValue = winreg.QueryValueEx(oKey, 'ProxyEnable')

        if dwValue[0] == 1:
            oKey = winreg.OpenKey(oReg, r'Software\Microsoft\Windows\CurrentVersion\Internet Settings')
            dwValue = winreg.QueryValueEx(oKey, 'ProxyServer')[0]
            self.isProxy = True
            self.proxy = dwValue

        self.proxyExclude = winreg.QueryValueEx(oKey, 'ProxyOverride')[0]

    def url_post(self, url, formData, user = None, passw = None, headers = {}):
        #For example: url_post('http://ipecho.net/', 'test=1')
        self.httpCOM.setOption(2, 13056)
        self.httpCOM.open('POST', url, False, user if user else None, passw if passw else None)
        self.httpCOM.setRequestHeader('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.107 Safari/537.36')
        #self.httpCOM.setRequestHeader('Content-Type', 'application/x-www-form-urlencoded')
        #self.httpCOM.setRequestHeader("Authorization", 'Basic ZGxKN2xWWDRHMVRSZkpoRFhBUDBuV1l0TG5MVjgwWG5EUXl0TW9hRzpBeWg1dGtiQnNYaUdRZnBUVEpNWVo2TFRrUlBON0tKWEVXNDZabjJ6ZVg0NTVLa3hFa0RzN1dESkk3YU9vRjNoTEtUZnFkOXZIYW90RW1uZTkxMHFGMjhwMUc2UFVpb2VsM1d4eUVtYkF1d09vaWVmdWdheEtuRkNRc2ZTMlVROQ==')
        for k,v in headers.items():
            self.httpCOM.setRequestHeader(k,v)
        self.httpCOM.send(formData)
        #print(user, passw,formData)
        # return self.httpCOM.responseText

    def url_get(self, url, user = None, passw = None, headers = {}):
        self.httpCOM.setOption(2, 13056)
        self.httpCOM.open('GET', url, False, user if user else None, passw if passw else None)
        self.httpCOM.setRequestHeader('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.107 Safari/537.36')
        for k,v in headers.items():
            self.httpCOM.setRequestHeader(k,v)
        self.httpCOM.send()
        # return self.httpCOM.responseText

    def get_text(self, func):
        @wraps(func)
        def wrapped(*args, **kwargs):
            func(*args,**kwargs)
            return self.httpCOM.responseText
        return wrapped

    def get_xml(self, func):
        @wraps(func)
        def wrapped(*args, **kwargs):
            func(*args,**kwargs)
            return self.httpCOM.responseXML
        return wrapped

    def get_status(self, func):
        @wraps(func)
        def wrapped(*args, **kwargs):
            func(*args,**kwargs)
            return str(self.httpCOM.status) + ': ' + self.httpCOM.statusText
        return wrapped

    def get_stream(self, func):
        @wraps(func)
        def wrapped(*args, **kwargs):
            func(*args,**kwargs)
            return self.httpCOM.responseStream
        return wrapped

    def get_bytes(self, func):
        @wraps(func)
        def wrapped(*args, **kwargs):
            func(*args,**kwargs)
            return self.httpCOM.responseBody
        return wrapped

    # def set_header(headers={}):
    #     for k,v in headers.items():
    #         self.httpCOM.setRequestHeader(k,v)

if __name__ == "__main__":
    http = HTTP_win()
    print(http.get_text(http.url_post)('https://stepik.org/oauth2/token/', 'grant_type=client_credentials', user='dlJ7lVX4G1TRfJhDXAP0nWYtLnLV80XnDQytMoaG', passw='Ayh5tkbBsXiGQfpTTJMYZ6LTkRPN7KJXEW46Zn2zeX455KkxEkDs7WDJI7aOoF3hLKTfqd9vHaotEmne910qF28p1G6PUioel3WxyEmbAuwOoiefugaxKnFCQsfS2UQ9'))
                                                                                                             