import os
import modal


stub = modal.Stub("github.commit")
pygithub_image = modal.Image.debian_slim().pip_install("PyGithub>=1.59")


with pygithub_image.imports():
    import github


@stub.function(
    image=pygithub_image, secrets=[modal.Secret.from_name("bots-doing-things")]
)
def create_file(repo: str, filename: str, commit: str, content: str):
    g = github.Github(os.getenv("GITHUB_API_TOKEN"))
    repo = g.get_repo(repo)
    repo.create_file(filename, commit, content)
