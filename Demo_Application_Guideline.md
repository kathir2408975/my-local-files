
# QEA-TCOE Multi-Agent Claims Automation & Assurance — Developer Guideline

## 📘 1. Project Overview
This project demonstrates an **AI-powered, multi-agent system** designed to automate and validate healthcare claim assurance workflows.  
Each agent in the system is responsible for a specific part of the process such as document analysis, claim validation, and decision-making.  
The application integrates **LLM-based reasoning**, configuration-driven execution, and modular design for scalability.

---

## 📁 2. Folder Structure

```
qea-tcoe-multiagent-claims-aut-assurance/
│
├── README.md                              → General project information
├── definitions.py                         → Global constants and shared definitions
├── requirements.txt                       → Python dependencies
├── configurations/
│   └── project_configurations.ini         → All project configuration parameters
│
├── src/
│   ├── common_layers/
│   │   └── llm_layer/
│   │       └── llm_manager.py            → Manages interaction with the LLM (Azure/OpenAI)
│   │
│   ├── common_utilities/
│   │   ├── configuration_loader.py       → Loads and parses configuration files
│   │   └── logger.py                     → Initializes structured logging
│   │
│   └── healthcare/
│       ├── agents/                       → Domain-specific agents
│       │   ├── claim_decision_agent.py   → Agent handling final claim decisions
│       │   ├── decision_agent.py         → Supports business rule–based decisions
│       │   └── document_agent.py         → Extracts and validates claim documents
│       │
│       ├── executor.py                   → Entry point to orchestrate agents
│       └── state.py                      → Maintains shared state between agents
│
├── .gitignore, .gitattributes            → Git version control settings
└── configurations/                       → Project-specific configurations
```

---

## 🧩 3. System Requirements

| Component | Recommended Version |
|------------|--------------------|
| Python | 3.9 or higher |
| pip | Latest |
| OS | Windows / Linux / macOS |
| Dependencies | Listed in `requirements.txt` 

Install required libraries using:
```bash
pip install -r requirements.txt
```

---
## 4. langsmith API key (Langsmith config)
 get the key from langsmith
 add your key to langsmith_keys.env

LANGCHAIN_PROJECT=  --> Add project
LANGCHAIN_API_KEY=  --> Add here API 
LANGCHAIN_ENDPOINT=https://api.smith.langchain.com --> this is common
LANGCHAIN_TRACING_V2=true --> this is common


## 🚀 5. Running the Application

Main execution starts from:
```
src/healthcare/executor.py
```

Run using:
```bash
python src/healthcare/executor.py
```

You can also import and run it from a notebook or script for testing individual agents.



## ✅ End of Guideline
You can now run the full demo or integrate new modules following this structure.

