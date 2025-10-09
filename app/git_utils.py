# git_utils.py
import subprocess


def push_to_git(repo_path, branch="main", commit_msg="Add new test script"):
    try:
        subprocess.run(["git", "-C", repo_path, "checkout", branch], check=True)
        subprocess.run(["git", "-C", repo_path, "pull"], check=True)
        subprocess.run(["git", "-C", repo_path, "add", "."], check=True)
        subprocess.run(["git", "-C", repo_path, "commit", "-m", commit_msg], check=True)
        subprocess.run(["git", "-C", repo_path, "push", "origin", branch], check=True)
        return True
    except subprocess.CalledProcessError as e:
        return False
