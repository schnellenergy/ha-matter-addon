#!/bin/bash

# This script pushes the add-on repository to GitHub

echo "Preparing to push the add-on repository to GitHub..."

# Initialize git repository if it doesn't exist
if [ ! -d ".git" ]; then
  echo "Initializing git repository..."
  git init
fi

# Add all files
echo "Adding files to git..."
git add .

# Commit changes
echo "Committing changes..."
git commit -m "Simplify Matter Controller add-on to use Alpine base image"

# Set the remote repository
echo "Setting remote repository..."
git remote remove origin 2>/dev/null
git remote add origin https://github.com/schnellenergy/ha-matter-addon.git

# Push to GitHub
echo "Pushing to GitHub..."
git push -u origin main --force

echo "Done! Now you can install the add-on from Home Assistant."
echo ""
echo "Repository pushed to GitHub!"
echo ""
echo "Now you can add the repository to Home Assistant:"
echo "1. In Home Assistant, go to Settings > Add-ons > Add-on Store"
echo "2. Click the three dots in the top-right corner"
echo "3. Select 'Repositories'"
echo "4. Add your repository URL: https://github.com/schnellenergy/ha-matter-addon"
echo "5. Click 'Add'"
echo "6. Find the add-ons in the list and install them"
echo ""
