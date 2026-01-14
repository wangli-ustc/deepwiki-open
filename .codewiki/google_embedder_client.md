# Google Embedder Client Module

The Google Embedder Client module provides integration with Google's AI Embeddings API, enabling semantic similarity, retrieval, and classification tasks through Google's embedding models. This module is part of the broader [api_model_clients](api_model_clients.md) system that handles various AI model integrations.

## Overview

The Google Embedder Client serves as a wrapper around Google's AI Embeddings API, providing a standardized interface for embedding text content. It supports both single and batch embedding operations and integrates seamlessly with the adalflow framework for embedding operations.

## Architecture

```mermaid
graph TB
    subgraph "Google Embedder Client"
        A[GoogleEmbedderClient] --> B[ModelClient Base]
        A --> C[Google AI API]
        A --> D[Embedding Processing]
    end
    
    subgraph "Integration Layer"
        E[adalflow Embedder] --> A
        F[API Layer] --> E
    end
    
    subgraph "External Dependencies"
        C --> G[Google Generative AI SDK]
        G --> H[Google AI Services]
    end
```

## Core Components

### GoogleEmbedderClient

The primary component of this module is the `GoogleEmbedderClient` class, which extends the `ModelClient` base class. This client handles:

- API key management and client initialization
- Input conversion to Google AI API format
- Embedding API calls with retry logic
- Response parsing to standard embedding format
- Error handling and logging

## Dependencies

```mermaid
graph LR
    A[GoogleEmbedderClient] --> B[adalflow.core.model_client]
    A --> C[google-generativeai SDK]
    A --> D[backoff library]
    B --> E[ModelClient Base]
    C --> F[Google AI Services]
```

## Data Flow

```mermaid
sequenceDiagram
    participant U as User/Service
    participant C as GoogleEmbedderClient
    participant G as Google AI API
    participant P as Response Parser
    
    U->>C: Input text + model parameters
    C->>C: Convert inputs to API format
    C->>G: Call Google AI Embeddings API
    G->>G: Process embedding request
    G->>C: Return embedding response
    C->>P: Parse response to EmbedderOutput
    C->>U: Return processed embeddings
```

## Component Interactions

```mermaid
graph LR
    A[External Service] --> B[GoogleEmbedderClient]
    B --> C[convert_inputs_to_api_kwargs]
    B --> D[call/acall]
    B --> E[parse_embedding_response]
    C --> F[Google AI API]
    D --> F
    E --> G[EmbedderOutput]
    F --> E
    G --> A
```

## Key Features

### API Key Management
- Supports both explicit API key and environment variable configuration
- Default environment variable: `GOOGLE_API_KEY`
- Automatic client initialization

### Input Processing
- Handles both single string and sequence of strings
- Converts inputs to Google AI API format
- Supports both single and batch embedding operations

### Response Handling
- Comprehensive response parsing with fallback mechanisms
- Error handling and logging
- Standardized `EmbedderOutput` format

### Retry Logic
- Implements exponential backoff for API calls
- Handles various Google AI API exceptions
- Configurable retry parameters

## Usage Example

```python
from api.google_embedder_client import GoogleEmbedderClient
import adalflow as adal

client = GoogleEmbedderClient()
embedder = adal.Embedder(
    model_client=client,
    model_kwargs={
        "model": "text-embedding-004",
        "task_type": "SEMANTIC_SIMILARITY"
    }
)
```

## Integration Points

This module integrates with:
- [api_model_clients](api_model_clients.md) for standardized model client interfaces
- [api.rag](api_rag.md) for retrieval-augmented generation capabilities
- The adalflow framework for embedding operations

## Error Handling

The client implements comprehensive error handling including:
- API key validation
- Input type validation
- Response parsing errors
- Google AI API exceptions
- Logging for debugging and monitoring

## Configuration

The client can be configured with:
- Custom API key
- Custom environment variable name for API key
- Model-specific parameters through `model_kwargs`
- Task types for different embedding scenarios

## Process Flow

```mermaid
flowchart TD
    A[Input Text] --> B{Single or Batch?}
    B -->|Single| C[Format as content]
    B -->|Batch| D[Format as contents]
    C --> E[Call Google AI API]
    D --> E
    E --> F[Parse Response]
    F --> G[Return EmbedderOutput]
    G --> H[Use in Application]
```

## Security Considerations

- API keys are handled securely through environment variables
- Input content is sanitized in logs
- Proper error handling prevents sensitive information exposure
- Follows Google AI API security best practices

## Performance Considerations

- Batch embedding support for efficiency
- Retry logic with exponential backoff
- Asynchronous call support (synchronous fallback)
- Memory-efficient response processing