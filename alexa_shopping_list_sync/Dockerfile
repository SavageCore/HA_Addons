ARG BUILD_FROM
FROM $BUILD_FROM

# Install necessary packages for the add-on, including Chromium and Chromedriver
RUN apk add --no-cache python3 py3-pip chromium chromium-chromedriver

# Set the working directory to the persistent data directory
WORKDIR /data

# Copy the application files to the container's /app directory
COPY app /app

# Navigate to the app directory
WORKDIR /app

# Create a virtual environment
RUN python3 -m venv /app/venv

# Activate the virtual environment and install Python dependencies
RUN /app/venv/bin/pip install --no-cache-dir -r requirements.txt

# Copy the run.sh script to the container and make it executable
COPY run.sh /
RUN chmod a+x /run.sh

# Set the default command to execute the run.sh script
CMD [ "/run.sh" ]
