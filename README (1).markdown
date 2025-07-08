# AI Tutor with Gemma3:1b and Docker

## Overview
AI Tutor is an intelligent educational tool powered by Ollama's Gemma3:1b model, containerized with Docker for easy deployment. It provides functionalities such as natural language response generation, quiz creation, PDF summarization, and more, making it a versatile assistant for students, educators, and knowledge seekers.

## Features
- **Response Generation**: Answer user queries with context-aware responses using Gemma3:1b.
- **Quiz Generation**: Automatically create quizzes based on input topics or content.
- **PDF Summarization**: Extract and summarize key points from uploaded PDF documents.
- **Docker Integration**: Run the application in a containerized environment for portability and scalability.
- **Streamlit Interface**: User-friendly web interface built with Streamlit for interacting with the AI Tutor.
- **Extensible Design**: Modular code structure allows for adding new features.

## Prerequisites
- [Docker](https://www.docker.com/get-started) installed on your system.
- [Git](https://git-scm.com/downloads) for cloning the repository.
- Basic familiarity with command-line interfaces.
- Optional: [Ollama](https://ollama.ai/) installed locally if you want to test the model outside Docker.

## Installation

1. **Clone the Repository**
   ```bash
   git clone https://github.com/ogulcanzorba/Docker_AI_Project.git
   cd Docker_AI_Project
   ```

2. **Build the Docker Image**
   The repository includes a `Dockerfile` that sets up the environment, installs dependencies, and pulls the Gemma3:1b model via Ollama.
   ```bash
   docker build -t ai-tutor .
   ```

3. **Run the Docker Container**
   Expose port 8501 (used by Streamlit) to access the web interface.
   ```bash
   docker run -p 8501:8501 ai-tutor
   ```

4. **Verify Setup**
   - Ensure the Gemma3:1b model is downloaded and loaded within the container (handled automatically by the `Dockerfile`).
   - Check that the Streamlit app is running by navigating to `http://localhost:8501` in your browser.

## Usage
- **Access the Web Interface**: Open `http://localhost:8501` to interact with the AI Tutor.
- **Response Generation**: Enter queries in the provided text input to receive answers powered by Gemma3:1b.
- **Quiz Generation**: Use the quiz feature to generate questions based on a topic or uploaded content.
- **PDF Summarization**: Upload a PDF file through the interface to receive a summarized version of its content.
- **Explore Additional Features**: Check the interface for other functionalities like topic exploration or content analysis.

## Project Structure
```
Docker_AI_Project/
├── Dockerfile           # Docker configuration for building the app
├── app.py              # Main Streamlit application script
├── requirements.txt    # Python dependencies (e.g., streamlit, ollama, PyPDF2)
├── README.md           # This documentation file
└── .gitignore          # Git ignore file for excluding unnecessary files
```

- **Dockerfile**: Defines the container setup, including Ubuntu base image, Ollama installation, Gemma3:1b model pull, and Python dependencies.
- **app.py**: Implements the Streamlit web interface and integrates with Ollama's Gemma3:1b model for AI functionalities.
- **requirements.txt**: Lists Python packages required for the application (e.g., `streamlit`, `ollama`, `PyPDF2`).

## Contributing
Contributions are welcome! To contribute:
1. Fork the repository.
2. Create a new branch (`git checkout -b feature/your-feature`).
3. Make your changes and commit (`git commit -m "Add your feature"`).
4. Push to the branch (`git push origin feature/your-feature`).
5. Open a Pull Request.

Please ensure your code adheres to the project's coding standards and includes appropriate documentation.

## Troubleshooting
- **Model Loading Issues**: Ensure sufficient disk space and memory for Gemma3:1b (check Docker logs with `docker logs <container_id>`).
- **Port Conflicts**: If port 8501 is in use, map a different host port (e.g., `docker run -p 8502:8501 ai-tutor`).
- **Dependency Errors**: Rebuild the Docker image to refresh dependencies (`docker build --no-cache -t ai-tutor .`).

## License
This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details (if added to the repository).

## Contact
For questions or support, open an issue on the [GitHub repository](https://github.com/ogulcanzorba/Docker_AI_Project) or contact the maintainer at [your-email@example.com].