import airflow
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.bash import BashOperator
from airflow.models import Variable

from datetime import datetime, timedelta
import json
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from airflow.providers.amazon.aws.operators.s3 import S3CreateObjectOperator
from airflow.providers.amazon.aws.hooks.s3 import S3Hook





# amazon s3 client
import boto3
from io import StringIO
import pandas as pd



# DEFAULT ARGUMENTS
default_args = {
    "owner":"nihitverma",
    "depents_on_past":False,
    "start_date": datetime(2024, 9,16),
}

dag = DAG(
    dag_id = "spotify_etl_dag",
    default_args=default_args,
    description="Spotfiy airflow etl pipeline dag",
    schedule_interval = timedelta(days=1),
    catchup=False
)

# Function for fetching the data from spotify api
def _fetch_spotify_data(**kwargs):
    client_id = Variable.get("spotify_client_id")
    client_secret = Variable.get("spotify_client_secret")
    
    client_credentials_manager = SpotifyClientCredentials(client_id=client_id , client_secret=client_secret)
    sp = spotipy.Spotify(client_credentials_manager=client_credentials_manager)
    
    playlists = sp.user_playlists('spotify')
    
    playlist_link = "https://open.spotify.com/playlist/37i9dQZEVXbMDoHDwVN2tF"
    playlist_URI = playlist_link.split('/')[-1]
    
    
    spotify_data = sp.playlist_tracks(playlist_URI)
    # print(spotify_data)
    
    # we have the data we will pass the data using xcom to another task - which will upload the task to s3 bucket
    
    filename = "spotify_raw_"+datetime.now().strftime("%Y%m%d%H%M%S") + ".json"
    
    kwargs['ti'].xcom_push(key='spotify_filename', value=filename)
    kwargs['ti'].xcom_push(key='spotify_data', value=json.dumps(spotify_data))


     
    
    

# fetch the data

fetch_data = PythonOperator(
    task_id = "fetch_spotify_data",
    python_callable=_fetch_spotify_data,
    dag = dag
)



# NOW WE HAVE THE DATA , WE WILL STORE THE DATA INTO S3 BUCKET FOLDER
# WE HAVE USED THE XCOM

store_raw_to_s3 = S3CreateObjectOperator(
    task_id = "upload_raw_to_s3",
    aws_conn_id="aws_conn",
    s3_bucket="spotify-data-project",
    s3_key="raw_data/to_processed/{{ task_instance.xcom_pull(task_ids='fetch_spotify_data', key='spotify_filename') }}",
    data="{{ task_instance.xcom_pull(task_ids='fetch_spotify_data', key='spotify_data') }}",
    replace=True,
    dag=dag
)


# READ THE DATA FROM AMAZON S3 BUCKET

def _read_data_from_s3(**kwargs):
    s3_hook = S3Hook(aws_conn_id="aws_conn")
    bucket_name = "spotify-data-project"
    prefix = "raw_data/to_processed/"
    keys = s3_hook.list_keys(bucket_name=bucket_name, prefix=prefix)
    
    spotify_data = []
    for key in keys:
        if key.endswith('.json'):
            data = s3_hook.read_key(key, bucket_name)
            spotify_data.append(json.loads(data))
            
    # Pushing the data to XCom for the next task to read it
    kwargs['ti'].xcom_push(key="spotify_data", value=spotify_data)


read_data_from_s3 = PythonOperator(
    task_id = "read_data_from_s3",
    python_callable=_read_data_from_s3,
    dag=dag
    
)


# NOW TRANSFORMING THE DATA AND STORING IN INDIVIDUAL FOLDERS

# read the data coming from xcom
def _process_album(**kwargs):
    spotify_data = kwargs['ti'].xcom_pull(task_ids="read_data_from_s3", key="spotify_data")
    album_list = []
    for data in spotify_data:    
        for row in data['items']:
            album_id = row['track']['album']['id']
            album_name = row['track']['album']['name']
            album_release_date = row['track']['album']['release_date']
            album_total_tracks = row['track']['album']['total_tracks']
            album_url = row['track']['album']['external_urls']['spotify']
            album_element = {'album_id':album_id,'name':album_name,'release_date':album_release_date,
                                'total_tracks':album_total_tracks,'url':album_url}
            album_list.append(album_element)
        
    album_df = pd.DataFrame.from_dict(album_list)
    album_df = album_df.drop_duplicates(subset=['album_id'])
    album_df['release_date'] = pd.to_datetime(album_df['release_date'])
    
    # send the content of the album using xcom


    # CONVERITNG THIS TO BUFFER
    album_buffer = StringIO()
    album_df.to_csv(album_buffer, index=False)
    album_content = album_buffer.getvalue()
    kwargs['ti'].xcom_push(key="album_content", value=album_content) 
    
    
       
    
    
    
def _process_artist(**kwargs):
    spotify_data = kwargs['ti'].xcom_pull(task_ids="read_data_from_s3", key="spotify_data")
    
    artist_list = []
    for data in spotify_data:
        for row in data['items']:
            for key, value in row.items():
                if key == "track":
                    for artist in value['artists']:
                        artist_dict = {'artist_id':artist['id'], 'artist_name':artist['name'], 'external_url': artist['href']}
                        artist_list.append(artist_dict)

    artist_df = pd.DataFrame.from_dict(artist_list)
    artist_df = artist_df.drop_duplicates(subset=['artist_id'])
    
    

    # CONVERITNG THIS TO BUFFER
    artist_buffer = StringIO()
    artist_df.to_csv(artist_buffer, index=False)
    artist_content = artist_buffer.getvalue()
    kwargs['ti'].xcom_push(key="artist_content", value=artist_content) 
    
    
    
    
def _process_songs(**kwargs):
    spotify_data = kwargs['ti'].xcom_pull(task_ids="read_data_from_s3", key="spotify_data")
    

    song_list = []
    for data in spotify_data:
        for row in data['items']:
            song_id = row['track']['id']
            song_name = row['track']['name']
            song_duration = row['track']['duration_ms']
            song_url = row['track']['external_urls']['spotify']
            song_popularity = row['track']['popularity']
            song_added = row['added_at']
            album_id = row['track']['album']['id']
            artist_id = row['track']['album']['artists'][0]['id']
            song_element = {'song_id':song_id,'song_name':song_name,'duration_ms':song_duration,'url':song_url,
                            'popularity':song_popularity,'song_added':song_added,'album_id':album_id,
                            'artist_id':artist_id
                        }
            song_list.append(song_element)
            
    song_df = pd.DataFrame.from_dict(song_list)
    song_df = song_df.drop_duplicates(subset=['artist_id'])



        
    # CONVERITNG THIS TO BUFFER
    song_buffer = StringIO()
    song_df.to_csv(song_buffer, index=False)
    song_content = song_buffer.getvalue()
    kwargs['ti'].xcom_push(key="song_content", value=song_content) 
    
    
    


# we have the data , we will take the proccessd data from the xcom 

# Processing function for each function 

process_album = PythonOperator(
    task_id = "process_album",
    python_callable=_process_album,
    provide_context= True
    
)
    
    
# NOW STORE THE DATA INTO AMAZON S3 , FOR THE ALBUM FILE 

store_album_to_s3 = S3CreateObjectOperator(
    task_id = "store_album_to_s3",
    aws_conn_id="aws_conn",
    s3_bucket="spotify-data-project",
    s3_key="transformed_data/album/album_transformed{{ ts_nodash }}.csv",
    data="{{ task_instance.xcom_pull(task_ids='process_album', key='album_content') }}",
    replace=True,
    dag=dag
)
    
# SAME WE DO FOR THE SONG AND ARTIST




process_artist = PythonOperator(
    task_id = "process_artist",
    python_callable=_process_artist,
    provide_context= True
    
)
    
    

store_artist_to_s3 = S3CreateObjectOperator(
    task_id = "store_artist_to_s3",
    aws_conn_id="aws_conn",
    s3_bucket="spotify-data-project",
    s3_key="transformed_data/artist/artist_transformed{{ ts_nodash }}.csv",
    data="{{ task_instance.xcom_pull(task_ids='process_artist', key='artist_content') }}",
    replace=True,
    dag=dag
)






process_songs = PythonOperator(
    task_id = "process_songs",
    python_callable=_process_songs,
    provide_context= True
    
)
    
    

store_songs_to_s3 = S3CreateObjectOperator(
    task_id = "store_songs_to_s3",
    aws_conn_id="aws_conn",
    s3_bucket="spotify-data-project",
    s3_key="transformed_data/songs/songs_transformed{{ ts_nodash }}.csv",
    data="{{ task_instance.xcom_pull(task_ids='process_songs', key='song_content') }}",
    replace=True,
    dag=dag
)
    
    

# USING THE FAN IN / OUT CONCEPT


def _move_data(**kwargs):
    s3_hook = S3Hook(aws_conn_id="aws_conn")
    bucket_name = "spotify-data-project"
    prefix = "raw_data/to_processed/"
    target_prefix = "raw_data/processed/"
    keys = s3_hook.list_keys(bucket_name=bucket_name, prefix=prefix)
    
    for key in keys:
        if key.endswith('.json'):
            new_key = key.replace(prefix , target_prefix)
            s3_hook.copy_object(
                source_bucket_key=key,
                dest_bucket_key=new_key,
                source_bucket_name=bucket_name,
                dest_bucket_name=bucket_name
            )
            
            s3_hook.delete_objects(
                bucket=bucket_name, keys=key
            )



move_data_task = PythonOperator(
    task_id = "move_data",
    python_callable=_move_data,
    provide_context=True,
    dag = dag
    
)


fetch_data >> store_raw_to_s3 
store_raw_to_s3 >> read_data_from_s3 
read_data_from_s3 >> process_album >> store_album_to_s3 
read_data_from_s3 >> process_artist >> store_artist_to_s3 
read_data_from_s3 >> process_songs >> store_songs_to_s3
[store_album_to_s3, store_artist_to_s3 , store_songs_to_s3] >>  move_data_task



# NOW WE MOVE ALL THE DATA FILES FROM to_processed TO processed AND DELETE THE FILE IN to_processed 

