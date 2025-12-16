FROM node:20-slim

WORKDIR /app

# Install wrangler, which includes miniflare v3
RUN npm install -g wrangler

# Expose the default wrangler dev port
EXPOSE 8787

# Command to run wrangler dev. This will automatically pick up the wrangler.toml
# from the working directory and start the local development server.
CMD ["wrangler", "dev"]
