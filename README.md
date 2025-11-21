# my-local-files
get the file in VM


1.submission_summery - revenues

query:

Total Revenues, Please indicate total REVENUES, SALES, total REVENUES, Revenues

2.cash and cash Equivalents

query:

Identify company's Cash and Cash Equivalents from the most recent year


3.current Asset

query:

what is the total amount for current Assets in the most recent fiscal year end (YE)?



4.open claim & valuation Date

query:

there is no semantic query

only prompt available



5.full-time employees in US

query:

How many Full-time U.S employees in the most recent year?



Your job is to go through the <chunks> and explain in great detail to fill out the JSON output.
1. List all the "Total Current Assets" and "Current Assets" values and the corresponding years they were recorded, and follow steps 2-4 for all the values:
2. Don't list years labeled as Estimates
3. If values are from a section that is described as being in units of thousands of dollars (examples: "000's", "$ in thousands"), append "000.00" to the value so it's in dollars before listing the value and its year
4. If values are present for multiple different entities, use the "Combined"/"Total" column
Return "" if no "Total Current Assets" and "Current Assets" values are found.
Answer only using information provided in the Document <chunks>; otherwise please leave that tag blank. Put your answer to the user inside the following JSON format:
thoughts: For each of the above numbered tasks, write down your findings task-by-task, one task at a time.
This is a space for you to write down relevant findings and will not be shown to the user.
Number your thoughts for each task with the corresponding task numbers above.
For each task of the above numbered tasks, identify all Chunk IDs where you found information in the <chunks> tag. Use \n for new lines for this value. Do not leave blank.
current_assets: The dollar value from the most recent/current full-year in the list from thoughts of all total Current Assets values
current_assets_source: Chunk ID where current_assets was sourced from
error_message: if you fail to make the extraction, explain why.
JSON struct output should not be enclosed in triple backticks; it should be output directly as JSON. Use default values ("") instead of null for any of the JSON values. Do not output any text outside the JSON. Do not include any new lines in the JSON struct output.
Think task-by-task and take your time.




26784619
Enter your query: Please indicate total REVENUES?

- Total revenues (2023): $24,054,787  
- Total revenues (2022): $18,381,040  ---> this correct
- Total revenues (2021): $22,983,401


58587108
Enter your query: Please indicate total REVENUES?
2022: $4,028,942, --->> this
2021: $4,222,971


26784619

Enter your query:
Identify company's Cash and Cash Equivalents from the most recent year?


"Cash and cash equivalents $ 6,755,020" --> correct



58587108
Enter your query:
Identify company's Cash and Cash Equivalents from the most recent year?
$2,305,577 --> correct



26784619

Enter your query:
what is the total amount for current Assets in the most recent fiscal year end (YE)?

"Information not found in the document."


58587108

Enter your query:
what is the total amount for current Assets in the most recent fiscal year end (YE)?

"Total current assets $3,052,326" --> correct


26784619

Enter your query:
How many Full-time U.S employees in the most recent year?
Information not found in the document. -->> wrong


58587108

Enter your query:
How many Full-time U.S employees in the most recent year?

0 -> correct


prompt 2:


26784619
Enter your query: Please indicate total REVENUES?

The total revenues for the most recent year (2023) are $24,054,787.


58587108
Enter your query: Please indicate total REVENUES?

The total revenues are as follows:  
- **2022:** $4,028,942  
- **2021:** $4,222,971


26784619

Enter your query:
Identify company's Cash and Cash Equivalents from the most recent year?

The company's Cash and Cash Equivalents from the most recent year is **$6,755,020**.





58587108
Enter your query:

Identify company's Cash and Cash Equivalents from the most recent year?

The company's Cash and Cash Equivalents from the most recent year (2023) are $2,305,577.


26784619
Enter your query: what is the total amount for current Assets in the most recent fiscal year end (YE)?

The total amount for current assets in the most recent fiscal year end (YE) is **$1,167,381**. -->> data taken from 2021, but ground value 2022 data



58587108
Enter your query: what is the total amount for current Assets in the most recent fiscal year end (YE)?


The total amount for current assets in the most recent fiscal year end (December 31, 2022) is **$3,052,326**.


26784619

Enter your query:

How many Full-time U.S employees in the most recent year?

The application indicates there are 13 full-time U.S. employees in the most recent year (10 in AL, CO, DE, FL, GA, KS, LA, ME, MO, MT, SC, TN, UT, WY, and 3 in "All Other States"). -->> correct


58587108

Enter your query:

How many Full-time U.S employees in the most recent year?

The Applicant reported 0 full-time U.S. employees in the most recent year.


from flask import Flask, request, jsonify
from ragas.metrics import (
    answer_relevancy,
    faithfulness,
    answer_correctness
)
from ragas import evaluate
from ragas.llms import LangchainLLM
from datasets import Dataset
from langchain_core.language_models import LLM
from typing import List
import requests

# ========== Custom LLM Wrapper ==========
class CustomLLM(LLM):
    def __init__(self, endpoint_url, headers=None, default_params=None):
        self.endpoint_url = endpoint_url
        self.headers = headers or {}
        self.default_params = default_params or {}

    @property
    def _llm_type(self) -> str:
        return "custom-llm"

    def _call(self, prompt: str, stop: List[str] = None) -> str:
        payload = self.default_params.copy()
        payload["prompt"] = prompt

        try:
            response = requests.post(
                self.endpoint_url,
                json=payload,
                headers=self.headers
            )
            response.raise_for_status()
            return response.json().get("response", "")  # Adjust this key as needed
        except Exception as e:
            raise RuntimeError(f"LLM API call failed: {e}")

# ========== Configuration ==========
LLM_API_URL = "http://your-llm-endpoint.com/api/generate"  # Replace with your endpoint
HEADERS = {
    "Authorization": "Bearer your_token",  # Replace with your token or auth header
    "Content-Type": "application/json"
}
DEFAULT_PARAMS = {
    "temperature": 0.7,
    "max_tokens": 300
}

# Register custom LLM with RAGAS
LangchainLLM(CustomLLM(LLM_API_URL, headers=HEADERS, default_params=DEFAULT_PARAMS))

# ========== Flask App ==========
app = Flask(__name__)

def build_dataset(data_list):
    return Dataset.from_list(data_list)

@app.route('/evaluate', methods=['POST'])
def evaluate_rag():
    data = request.get_json()

    if not data or 'samples' not in data:
        return jsonify({'error': 'Invalid request. "samples" field is required.'}), 400

    try:
        dataset = build_dataset(data['samples'])

        result = evaluate(
            dataset,
            metrics=[
                answer_relevancy,
                faithfulness,
                answer_correctness,
            ]
        )

        return jsonify(result.to_dict()), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ========== Run App ==========
if __name__ == '__main__':
    app.run(debug=True)






