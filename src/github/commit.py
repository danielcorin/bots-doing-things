import os
import modal
from typing import Dict


app = modal.App("github.commit")
pygithub_image = modal.Image.debian_slim().pip_install("PyGithub>=1.59")


with pygithub_image.imports():
    import github


@app.function(
    image=pygithub_image, secrets=[modal.Secret.from_name("bots-doing-things")]
)
def create_file(repo: str, filename: str, commit: str, content: str):
    g = github.Github(os.getenv("GITHUB_API_TOKEN"))
    repo = g.get_repo(repo)
    repo.create_file(filename, commit, content)


@app.function(
    image=pygithub_image, secrets=[modal.Secret.from_name("bots-doing-things")]
)
def create_files(repo: str, files: Dict[str, str], commit: str):
    g = github.Github(os.getenv("GITHUB_API_TOKEN"))
    repo = g.get_repo(repo)

    # Create a new Git tree with the new files
    base_tree = repo.get_git_tree(repo.get_branch("main").commit.sha)
    tree_elements = []
    for filename, content in files.items():
        blob = repo.create_git_blob(content, "utf-8")
        tree_elements.append(
            github.InputGitTreeElement(
                path=filename, mode="100644", type="blob", sha=blob.sha
            )
        )
    new_tree = repo.create_git_tree(tree_elements, base_tree)

    # Create a new commit
    parent = repo.get_branch("main").commit
    parent_git_commit = repo.get_git_commit(parent.sha)  # Convert Commit to GitCommit
    new_commit = repo.create_git_commit(commit, new_tree, [parent_git_commit])

    # Update the main branch reference
    ref = repo.get_git_ref("heads/main")
    ref.edit(new_commit.sha)
