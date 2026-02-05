# Running the RFQ Intelligence Python Backend

## Prerequisites
- Python 3.9+ installed
- `mistralai` API Key in `.env.local`

## Installation
1.  Navigate to the project root.
2.  Run the setup script to install dependencies and the German NLP model:
    ```powershell
    .\python\setup_env.bat
    ```

## Starting the Server
1.  Go to the python directory:
    ```powershell
    cd python
    ```
2.  Start the FastAPI server:
    ```powershell
    uvicorn main:app --reload
    ```
    The server will start at `http://localhost:8000`.

## API Usage
**Endpoint**: `POST http://localhost:8000/process`

**Body**: `multipart/form-data`
- `file`: The PDF or Image file.

**Response**:
```json
{
  "status": "success",
  "metadata": { ... },
  "header": { "rfq_number": "12345", ... },
  "data": { "requested_items": [ ... ] }
}
```
