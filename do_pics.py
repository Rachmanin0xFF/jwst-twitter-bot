import configparser
import tweepy
import pathlib

config = configparser.ConfigParser()
config.read('C:\\Users\\Adam\\Documents\\jwst-twitter-bot\\config.ini')
print(config.sections())

bearer_token = config['twitter']['bearer_token']

consumer_key = config['twitter']['consumer_key']
consumer_key_secret = config['twitter']['consumer_key_secret']

access_token = config['twitter']['access_token']
access_token_secret = config['twitter']['access_token_secret']

# V2 Authentication does not yet support posting media
# client = tweepy.Client(consumer_key=consumer_key,
#                        consumer_secret=consumer_key_secret,
#                        access_token=access_token,
#                        access_token_secret=access_token_secret)

auth=tweepy.OAuthHandler(consumer_key,consumer_key_secret)
auth.set_access_token(access_token,access_token_secret)
api=tweepy.API(auth)

def post_images(paths, description="test image"):
    media_ids = []
    for x in paths:
        res = api.media_upload(str(pathlib.Path(__file__).parent.resolve()) + "\\" + x)
        media_ids.append(res.media_id)
        if len(media_ids) == 4:
            break
    status = api.update_status(status=description, media_ids=media_ids)

#print("client created...")
post_images(paths=["test.png"], description="Test image!")
#response = client.create_tweet(
#    text="Calibrating sensors..."
#)
#print(f"https://twitter.com/user/status/{response.data['id']}")

#print(client)
#print(client.follow(target_user_id="1244334289895993345"))
#print("followed...")