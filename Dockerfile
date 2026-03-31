# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set the working directory in the container
WORKDIR /app

# Prevent Python from writing pyc files to disc (optional)
ENV PYTHONDONTWRITEBYTECODE 1
# Ensure Python output is sent straight to terminal (useful for logging)
ENV PYTHONUNBUFFERED 1

# Install system dependencies if needed (e.g., for libraries that compile C code)
# We likely don't need extra system dependencies for these libraries

# Install Python dependencies
# Copy the requirements file first to leverage Docker cache
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code into the container
# Ensure .dockerignore is set up to exclude .venv, .git, etc.
COPY . .

# Expose the port the app runs on (should match Uvicorn command)
ENV PORT 8080

# Expose the port
EXPOSE 8080

# Command to run the application, using the $PORT variable
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT}

# Define the command to run the application using Uvicorn
# Use 0.0.0.0 to bind to all interfaces inside the container
