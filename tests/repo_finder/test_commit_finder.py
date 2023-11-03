# Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module tests the commit finder."""
import os
import shutil
from pathlib import Path

from pydriller import Git

from macaron.repo_finder import commit_finder
from tests.slsa_analyzer.mock_git_utils import add_new_commit_with_tag, initiate_repo


def test_get_commit_from_version() -> None:
    """Test resolving commits from version tags."""
    path = Path(__file__).parent.joinpath("mock_repo")
    if os.path.exists(path):
        shutil.rmtree(path)
    git_obj: Git = initiate_repo(path)

    tags = ["test-name-v1.0.1-A", "v1.0.3+test", "v_1.0.5", "50_0_2", "r78rv109", "1.0.5-JRE"]
    # Add a commit for each tag that can be verified later.
    hash_targets = []
    for tag in tags:
        hash_targets.append(add_new_commit_with_tag(git_obj, tag))

    # Perform tests
    versions = [
        "1.0.1-A",  # To match a tag with a named suffix.
        "1.0.3+test",  # To match a tag with a '+' suffix.
        "1.0.5",  # To match a tag with a 'v_' prefix.
        "50.0.2",  # To match a tag separated by '_'.
        "78.109",  # To match a tag separated by characters 'r' 'rv'.
        "1.0.5-JRE",  # To NOT match the similar tag without the 'JRE' suffix.
    ]
    purl_name = "test-name"
    for count, value in enumerate(versions):
        _test_version(git_obj, purl_name, value, hash_targets[count])
        purl_name = "test-name" + "-" + str(count + 1)


def _test_version(git_obj: Git, name: str, version: str, hash_target: str) -> None:
    """Retrieve commit matching version and check commit hash is correct."""
    branch, digest = commit_finder.get_commit_from_version(git_obj, name, version)
    assert branch
    assert git_obj.get_commit(digest).hash == hash_target
