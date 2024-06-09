import moviepy.editor as mp
from moviepy.editor import ColorClip,TextClip,AudioFileClip
import requests
import os
from pprint import pprint

VIDEO_PATH="./videos"
GIF_PATH="./gifs"
os.makedirs(VIDEO_PATH, exist_ok=True)
os.makedirs(GIF_PATH, exist_ok=True)

GIPHY_ENDPOINT="https://api.giphy.com/v1/gifs/search"

"""
Download new gifs to keep the gif stockpile fresh, adds key value pair to redis
"""
def loadRedisWithGIFS(redis_server, api_key, endpoint=GIPHY_ENDPOINT, search_term="aesthetic anime", limit=25):
    params = {
        'q': search_term,
        'api_key': api_key,
        'rating': 'pg-13', #general,
        'limit': limit
    }
    res = requests.get(url=endpoint, params=params)
    retcode = res.json()['meta']['status']

    # download the gif    
    for gif in res.json()['data']:
        gif_id = "gif:" + gif['id']
        
        # gets the original version's direct url.
        gif_url = gif['images']['original']['url']
        
        # only add new gifs to the redis server
        if not redis_server.exists(gif_id):
            redis_server.hset(gif_id, "gif_url", gif_url)
            redis_server.hset(gif_id, "visited", 0)

    return retcode, gif_id, gif_url

def getNotVisitedHeper(redis_server):
    cursor = 0
    while True: 
        cursor, keys = redis_server.scan(cursor=cursor, match='gif:*', count=100)
        for key in keys:
            visited = redis_server.hget(key, 'visited')
            if visited == b'0':
                # found key that has not been visited
                value = redis_server.hgetall(key)
                
                return key, value[b'gif_url'].decode('utf-8')
        if cursor == 0:
            break 
    return "NULL"

"""
Searches redis for new gifs that have visited flag set to 0, returns the gif path from the url of that gif
if we cant find anything, then we will have to call loadRedisWithGIFS again, or with another search term
"""
def getNotVisited(redis_server, api_key):
    
    res = getNotVisitedHeper(redis_server)
    if res != "NULL":
        return res
    
    # did not find, try to search again:
    loadRedisWithGIFS(redis_server, api_key)
    res = getNotVisitedHeper(redis_server)
    if res != "NULL":
        return res
        
    # still didnt find!!! we will use trending.
    loadRedisWithGIFS(api_key, search_term="trending", limit=5)
    res = getNotVisitedHeper(redis_server)
    return res


"""
Helper to download the gif from the url, and save to path
returns output path
"""
def downloadGIF(gif_id, gif_url):
    print("Getting Request for GIF...")
    headers = {'User-Agent': 'Mozilla/5.0'}
    response = requests.get(gif_url, headers=headers)
    save_path = os.path.join(GIF_PATH, gif_id.decode('utf-8')[4:] + ".gif")
    
    # Check if the request was successful (status code 200)
    if response.status_code == 200:
        # Open the file and write the content of the response
        with open(save_path, 'wb') as f:
            f.write(response.content)
        print(f'GIF saved to {save_path}')
    else:
        print(f'Failed to download GIF. Status code: {response.status_code}')

    return save_path

"""
downloads a fresh gif and returns the output path
"""
def getNewGIF(redis_server, api_key):
    
    # get a fresh gif
    key, gif_url = getNotVisited(redis_server, api_key)
    
    output_path = downloadGIF(key, gif_url)
    
    # set visited to true
    redis_server.hset(key, "visited", 1)
    return output_path
     
def createVideoFromGIF(audio_path, gif_path, yt_vidname):
    
    audio_track = AudioFileClip(audio_path)

    #dark background
    hdres = [1280, 720]
    black_clip = ColorClip(size = hdres, color = [0,0,0]).set_duration(audio_track.duration)

    #selected GIF
    animated_gif = (mp.VideoFileClip(gif_path)
            .resize(width=int(0.5 * black_clip.size[0]), height=int(0.5 * black_clip.size[1]))
            .loop()
            .set_duration(audio_track.duration)
            .set_pos(("center","center")))

    #custom made formula to set words below the animated GIF
    var_y = 0.5 * (black_clip.size[1] - animated_gif.size[1])
    new_y = animated_gif.size[1] + 1.25 * var_y
    new_x = "center" 

    title_clip = TextClip(txt=yt_vidname, fontsize=30, font='Brush-Script-MT-Italic', color='white')
    title = title_clip.set_pos((new_x,new_y)).set_duration(audio_track.duration)

    setaudioclip = animated_gif.set_audio(audio_track)

    file_basename = yt_vidname.replace(' ', '')
    final = mp.CompositeVideoClip([black_clip, setaudioclip, title])
    final.write_videofile(os.path.join(VIDEO_PATH, file_basename))

    