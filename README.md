
# Spotify ETL Data Pipeline


## Technologies Used
- Apache Airflow: Workflow orchestration for managing the ETL process.
- Spotify API: Extracts playlists, tracks, and metadata from Spotify using spotipy.
- Amazon S3: Storage solution for raw and transformed data.
- boto3: Python SDK for interfacing with Amazon S3.
- Pandas: Used for data transformation (e.g., processing albums, artists, and songs).
- Python XComs: Used to pass data between tasks in Airflow.



## Pipeline Structure

- Extraction: The pipeline uses spotipy to fetch playlist tracks from the Spotify API.

    - Task: 

- Raw Data Storage: Stores the raw Spotify data in an S3 bucket.
    - Task: upload_raw_to_s3
- Data Transformation:
    The pipeline reads the raw JSON data from S3.
    Data is transformed into albums, artists, and songs using Pandas DataFrames.
    Tasks:
    process_album
    process_artist
    process_songs

- Transformed Data Storage: The processed data (albums, artists, songs) is stored back in S3.

    - Tasks:
        - store_album_to_s3
        - store_artist_to_s3
        - store_songs_to_s3

- Data Movement: Moves processed data to a different S3 folder and deletes the raw data.

    - Task: move_data
## Methodology



- Fan In/Out Pattern: The pipeline implements the fan-in/fan-out pattern, where multiple parallel tasks process different aspects of the data (albums, artists, songs), and then consolidate the processed data for storage.

- XCom for Task Communication: XCom is utilized to pass extracted and processed data between tasks, ensuring smooth data flow across different stages of the pipeline.


## Project Setup

pip install apache-airflow boto3 pandas spotipy



![spotify-airflow-project](https://github.com/user-attachments/assets/61b37c78-b6b6-42c0-8525-d703a8c721e2)

## 🔗 Links


