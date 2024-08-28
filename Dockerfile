# Use the official Python image from the Docker Hub with version 3.10
FROM python:3.10-slim

# Set the working directory inside the container
WORKDIR /app

# Copy the current directory contents into the container at /app
COPY . /app

# Install any required packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Make port 8080 available to the world outside this container (if needed)
EXPOSE 8080

# Run main.py when the container launches
CMD ["python", "main.py"]
