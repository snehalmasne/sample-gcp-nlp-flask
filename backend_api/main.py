from datetime import datetime
import logging
from flask import Flask
from flask_restx import Resource, Api
from google.cloud import datastore
from google.cloud import language_v1 as language
import os
import requests
from bs4 import BeautifulSoup

os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "key.json"

# ########### MAKE SURE YOU HAVE RUN BELOW CODE BEFORE INVOKING main.py #######
#  pip install -r requirements.txt
#  pip install virtualenv
#  virtualenv -p python3 env
#  source env/bin/activate
######################################################

"""
This Flask app shows some examples of the types of requests you could build.
There is currently a GET request that will return all the data in GCP Datastore.
There is also a POST request that will analyse some given text then store the text and its sentiment in GCP Datastore.


The sentiment analysis of the text is being done by Google's NLP API. 
This API can be used to find the Sentiment, Entities, Entity-Sentiment, Syntax, and Content-classification of texts.
Find more about this API here:
https://cloud.google.com/natural-language/docs/basics
For sample code for implementation, look here (click 'Python' above the code samples):
https://cloud.google.com/natural-language/docs/how-to
Note: The analyze_text_sentiment() method below simply copies the 'Sentiment' part of the above documentation.


The database we are using is GCP Datastore (AKA Firestore in Datastore mode). 
This is a simple NoSQL Document database offering by Google:
https://cloud.google.com/datastore
You can access the database through the GCP Cloud Console (find Datastore in the side-menu)


Some ideas of things to build:
- At the moment, the code only stores the analysis of the first sentence of a given text. Modify the POST request to
 also analyse the rest of the sentences. 
- GET Request that returns a single entity based on its ID
- POST Request that will take a list of text items and give it a sentiment then store it in GCP Datastore
- DELETE Request to delete an entity from Datastore based on its ID
- Implement the other analyses that are possible with Google's NLP API


We are using Flask: https://flask.palletsprojects.com/en/2.0.x/
Flask RESTX is an extension of Flask that allows us to document the API with Swagger: https://flask-restx.readthedocs.io/en/latest/
"""

app = Flask(__name__)
api = Api(app)

parser = api.parser()
parser.add_argument("text", type=str, help="Text", location="form")
parser.add_argument("urls", type=str, help="urls", location="form")


@api.route("/api/text")
class Text(Resource):
    def get(self):
        """
        This GET request will return all the texts,sentiments, entities and topics that have been POSTed previously.
        """
        # Create a Cloud Datastore client.
        datastore_client = datastore.Client()

        # Get the datastore 'kind' which are 'Sentences', 'Entities' & 'Topics'
        query = datastore_client.query(kind="Sentences")
        text_entities = list(query.fetch())

        # Parse the data into a dictionary format
        result = {}
        for text_entity in text_entities:
            result[str(text_entity.id)] = {
                "text": str(text_entity["text"]),
                "timestamp": str(text_entity["timestamp"]),
                "sentiment": str(text_entity["sentiment"]),
            }
          
        return result
          
        query = datastore_client.query(kind="Entities")
        salience_entities = list(query.fetch())

        # Parse the data into a dictionary format
        result = {}
        for salience_entity in salience_entities:
            result[float(salience_entity.id)] = {
                "salience": float(salience_entity["salience"]),
                "timestamp": str(text_entity["name"]),
                "sentiment": str(text_entity["type"]),
            }
          
          

        return result

    @api.expect(parser)
    def post(self):
        """
        This POST request can be used in two ways. Either provide the text to be analysed or provide comma separated list of URL to fetch the data from. The url takes precedence over text.
        """
        args = parser.parse_args()
        text = args["text"]
        urls = args["urls"]
        urls = urls.split(',')
        for url in urls:
            print("Processing : " + url)
            text = scrapeDataFromUrl(url)
            analyseSentimentAndPersistToDataStore(text)
            analyseEntitiesAndPersistToDataStore(text)

def scrapeDataFromUrl(url):
    print("Scraping : " + url)
    req = requests.get(url)
    soup = BeautifulSoup(req.text,"html.parser")
    text_elements = soup.find_all("div",{'class':'rich-text'})
    result = text_elements[0].text
    print('Scraped text = ' + result)
    return result

def analyseEntitiesAndPersistToDataStore(text):
    datastore_client = datastore.Client()
    entities_result = analyze_entities(text)  # this is a list
    print("Entities result from GCP NLP API = ", entities_result, sep = ',')

    for entity_result in entities_result:
        # The kind for the new entity. This is so all 'Sentences' can be queried.
        kind = "Entities"

        # Create a key to store into datastore
        key = datastore_client.key(kind)

        # Construct the new entity using the key. Set dictionary values for entity
        entity = datastore.Entity(key)

        name_str = entity_result["name"]
        print("name_str = " + name_str)

        entity["name"] = name_str
        entity["type"] = entity_result["type"]
        entity["salience"] = entity_result["salience"]

        # Save the new entity to Datastore.
        datastore_client.put(entity)


def analyseSentimentAndPersistToDataStore(text):
    datastore_client = datastore.Client()

    # Get the sentiment score of the first sentence of the analysis (that's the [0] part)
    # the text can have multiple lines and NLP API result will be a list, an item for each of the line in the text
    sentiment_result = analyze_text_sentiment(text)  # this is a list
    print("Sentiment result from GCP NLP API = ", sentiment_result, sep = ',')
    for sentimentRecord in sentiment_result:
        sentiment = sentimentRecord.get("sentiment score")
        sentiment_text = sentimentRecord.get("text")

        # Assign a label based on the score
        overall_sentiment = "unknown"
        if sentiment > 0:
            overall_sentiment = "positive"
        if sentiment < 0:
            overall_sentiment = "negative"
        if sentiment == 0:
            overall_sentiment = "neutral"

        current_datetime = datetime.now()

        # The kind for the new entity. This is so all 'Sentences' can be queried.
        kind = "Sentences"

        # Create a key to store into datastore
        key = datastore_client.key(kind)
        # If a key id is not specified then datastore will automatically generate one. For example, if we had:
        # key = datastore_client.key(kind, 'sample_task')
        # instead of the above, then 'sample_task' would be the key id used.

        # Construct the new entity using the key. Set dictionary values for entity
        entity = datastore.Entity(key)
        entity["text"] = sentiment_text
        entity["timestamp"] = current_datetime
        entity["sentiment"] = overall_sentiment

        # Save the new entity to Datastore.
        datastore_client.put(entity)

#             result = {}
#             result[str(entity.key.id)] = {
#                 "text": text,
#                 "timestamp": str(current_datetime),
#                 "sentiment": overall_sentiment,
#             }
#             return result


@app.errorhandler(500)
def server_error(e):
    logging.exception("An error occurred during a request.")
    return (
        """
    An internal error occurred: <pre>{}</pre>
    See logs for full stacktrace.
    """.format(
            e
        ),
        500,
    )

def analyze_entities(text):
    """
    This is modified from the Google NLP API documentation found here:
    https://cloud.google.com/natural-language/docs/analyzing-sentiment
    It makes a call to the Google NLP API to retrieve sentiment analysis.
    """
    client = language.LanguageServiceClient()
    document = language.Document(content=text, type_=language.Document.Type.PLAIN_TEXT)
    response = client.analyze_entities(document=document)

    final_result = []
    for entity_result in response.entities:
        result_record = {}
        result_record["text"] = text
        result_record["name"] = entity_result.name
        result_record["type"] = entity_result.type_
        result_record["salience"] = entity_result.salience
        final_result.append(result_record)

    return final_result



def analyze_text_sentiment(text):
    """
    This is modified from the Google NLP API documentation found here:
    https://cloud.google.com/natural-language/docs/analyzing-sentiment
    It makes a call to the Google NLP API to retrieve sentiment analysis.
    """
    client = language.LanguageServiceClient()
    document = language.Document(content=text, type_=language.Document.Type.PLAIN_TEXT)

    response = client.analyze_sentiment(document=document)

    # Format the results as a dictionary
    sentiment = response.document_sentiment
    results = dict(
        text=text,
        score=f"{sentiment.score:.1%}",
        magnitude=f"{sentiment.magnitude:.1%}",
    )

    # Print the results for observation
    for k, v in results.items():
        print(f"{k:10}: {v}")

    # Get sentiment for all sentences in the document
    sentence_sentiment = []
    for sentence in response.sentences:
        item = {}
        item["text"] = sentence.text.content
        item["sentiment score"] = sentence.sentiment.score
        item["sentiment magnitude"] = sentence.sentiment.magnitude
        sentence_sentiment.append(item)

    return sentence_sentiment


if __name__ == "__main__":
    # This is used when running locally. Gunicorn is used to run the
    # application on Google App Engine. See entrypoint in app.yaml.
    app.run(host="127.0.0.1", port=8080, debug=True)
