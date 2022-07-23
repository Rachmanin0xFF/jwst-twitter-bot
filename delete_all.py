import configparser
import tweepy
import pathlib

config = configparser.ConfigParser()
config.read('config.ini')

consumer_key = config['twitter']['consumer_key']
consumer_key_secret = config['twitter']['consumer_key_secret']

access_token = config['twitter']['access_token']
access_token_secret = config['twitter']['access_token_secret']

auth=tweepy.OAuthHandler(consumer_key,consumer_key_secret)
auth.set_access_token(access_token,access_token_secret)
api=tweepy.API(auth)

def batch_delete(api):
    print(
        "You are about to delete all tweets from the account @%s."
        % api.verify_credentials().screen_name
    )
    print("Does this sound ok? There is no undo! Type yes to carry out this action.")
    do_delete = input("> ")
    if do_delete.lower() == "yes":
        for status in tweepy.Cursor(api.user_timeline).items():
            try:
                api.destroy_status(status.id)
                print("Deleted:", status.id)
            except Exception:
                traceback.print_exc()
                print("Failed to delete:", status.id)

batch_delete(api)