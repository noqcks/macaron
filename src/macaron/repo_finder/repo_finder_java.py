# Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the JavaRepoFinder class to be used for finding Java repositories."""
import logging
import re
from xml.etree.ElementTree import Element  # nosec

import defusedxml.ElementTree
from defusedxml.ElementTree import fromstring
from packageurl import PackageURL

from macaron.config.defaults import defaults
from macaron.repo_finder.repo_finder_base import BaseRepoFinder
from macaron.repo_finder.repo_validator import find_valid_repository_url
from macaron.util import send_get_http_raw

logger: logging.Logger = logging.getLogger(__name__)


class JavaRepoFinder(BaseRepoFinder):
    """This class is used to find Java repositories."""

    def __init__(self) -> None:
        """Initialise the Java repository finder instance."""
        self.pom_element: Element | None = None

    def find_repo(self, purl: PackageURL) -> str:
        """
        Attempt to retrieve a repository URL that matches the passed artifact.

        Parameters
        ----------
        purl : PackageURL
            The PURL of an artifact.

        Yields
        ------
        str :
            The URL of the found repository.
        """
        # Perform the following in a loop:
        # - Create URLs for the current artifact POM
        # - Parse the POM
        # - Try to extract SCM metadata and return URLs
        # - Try to extract parent information and change current artifact to it
        # - Repeat
        group = purl.namespace or ""
        artifact = purl.name
        version = purl.version or ""
        limit = defaults.getint("repofinder.java", "parent_limit", fallback=10)

        if not version:
            logger.debug("Version missing for maven artifact: %s:%s", group, artifact)
            # TODO add support for Java artifacts without a version
            return ""

        while group and artifact and version and limit > 0:
            # Create the URLs for retrieving the artifact's POM
            group = group.replace(".", "/")
            request_urls = self._create_urls(group, artifact, version)
            if not request_urls:
                # Abort if no URLs were created
                logger.debug("Failed to create request URLs for %s:%s:%s", group, artifact, version)
                return ""

            # Try each POM URL in order, terminating early if a match is found
            pom = ""
            for request_url in request_urls:
                pom = self._retrieve_pom(request_url)
                if pom != "":
                    break

            if pom == "":
                # Abort if no POM was found
                logger.debug("No POM found for %s:%s:%s", group, artifact, version)
                return ""

            urls = self._read_pom(pom)

            if urls:
                # If the found URLs fail to validate, finding can continue on to the next parent POM
                logger.debug("Found %s urls: %s", len(urls), urls)
                url = find_valid_repository_url(urls)
                if url:
                    logger.debug("Found valid url: %s", url)
                    return url

            if defaults.getboolean("repofinder.java", "find_parents") and self.pom_element is not None:
                # Attempt to extract parent information from POM
                group, artifact, version = self._find_parent(self.pom_element)
            else:
                break

            limit = limit - 1

        # Nothing found
        return ""

    def _create_urls(self, group: str, artifact: str, version: str) -> list[str]:
        """
        Create the urls to search for the pom relating to the passed artifact.

        Parameters
        ----------
        group : str
            The group ID.
        artifact: str
            The artifact ID.
        version: str
            The version of the artifact.

        Returns
        -------
        list[str]
            The list of created URLs.
        """
        repositories = defaults.get_list(
            "repofinder.java", "artifact_repositories", fallback=["https://repo.maven.apache.org/maven2"]
        )
        urls = []
        for repo in repositories:
            urls.append(f"{repo}/{group}/{artifact}/{version}/{artifact}-{version}.pom")
        return urls

    def _retrieve_pom(self, url: str) -> str:
        """
        Attempt to retrieve the file located at the passed URL.

        Parameters
        ----------
        url : str
            The URL for the GET request.

        Returns
        -------
        str :
            The retrieved file data or an empty string.
        """
        response = send_get_http_raw(url, {})

        if not response:
            return ""

        logger.debug("Found artifact POM at: %s", url)
        return response.text

    def _read_pom(self, pom: str) -> list[str]:
        """
        Parse the passed pom and extract the relevant tags.

        Parameters
        ----------
        pom : str
            The pom as a string.

        Returns
        -------
        list[str] :
            The extracted contents as a list of strings.
        """
        # Retrieve tags
        tags = defaults.get_list("repofinder.java", "repo_pom_paths")
        if not any(tags):
            logger.debug("No POM tags found for URL discovery.")
            return []

        # Parse POM using defusedxml
        pom_element = self._parse_pom(pom)
        if pom_element is None:
            return []

        # Attempt to extract SCM data and return URL
        return self._find_scm(pom_element, tags)

    def _parse_pom(self, pom: str) -> Element | None:
        """
        Parse the passed POM using defusedxml.

        Parameters
        ----------
        pom : str
            The contents of a POM file as a string.

        Returns
        -------
        Element | None :
            The parsed element representing the POM's XML hierarchy.
        """
        try:
            self.pom_element = fromstring(pom)
            return self.pom_element
        except defusedxml.ElementTree.ParseError as error:
            logger.debug("Failed to parse XML: %s", error)
            return None

    def _find_scm(self, pom: Element, tags: list[str], resolve_properties: bool = True) -> list[str]:
        """
        Parse the passed pom and extract the passed tags.

        Parameters
        ----------
        pom : Element
            The parsed POM.
        tags : list[str]
            The list of tags to try extracting from the POM.
        resolve_properties: bool
            Whether to attempt resolution of Maven properties within the POM.

        Returns
        -------
        list[str] :
            The extracted contents of any matches tags as a list of strings.
        """
        results = []

        # Try to match each tag with the contents of the POM.
        for tag in tags:
            element: Element | None = pom

            if tag.startswith("properties."):
                # Tags under properties are often "." separated
                # These can be safely split into two resulting tags as nested tags are not allowed here
                tag_parts = ["properties", tag[11:]]
            else:
                # Other tags can be split into distinct elements via "."
                tag_parts = tag.split(".")

            for index, tag_part in enumerate(tag_parts):
                element = self._find_element(element, tag_part)
                if element is None:
                    break
                if index == len(tag_parts) - 1 and element.text:
                    # Add the contents of the final tag
                    results.append(element.text.strip())

        # Resolve any Maven properties within the results
        if resolve_properties:
            results = self._resolve_properties(pom, results)

        return results

    def _find_parent(self, pom: Element) -> tuple[str, str, str]:
        """
        Extract parent information from passed POM.

        Parameters
        ----------
        pom : str
            The POM as a string.

        Returns
        -------
        tuple[str] :
            The GAV of the parent artifact.
        """
        element = self._find_element(pom, "parent")
        if element is None:
            return "", "", ""
        group = self._find_element(element, "groupId")
        artifact = self._find_element(element, "artifactId")
        version = self._find_element(element, "version")
        if (
            group is not None
            and group.text
            and artifact is not None
            and artifact.text
            and version is not None
            and version.text
        ):
            return group.text.strip(), artifact.text.strip(), version.text.strip()
        return "", "", ""

    def _find_element(self, parent: Element | None, target: str) -> Element | None:
        if not parent:
            return None

        # Attempt to match the target tag within the children of parent.
        for child in parent:
            # Handle raw tags, and tags accompanied by Maven metadata enclosed in curly braces. E.g. '{metadata}tag'
            if child.tag == target or child.tag.endswith(f"}}{target}"):
                return child
        return None

    def _resolve_properties(self, pom: Element, values: list[str]) -> list[str]:
        """Resolve any Maven properties found within the passed list of values.

        Maven POM files have five different use cases for properties (see https://maven.apache.org/pom.html).
        Only the two that relate to contents found elsewhere within the same POM file are considered here.
        That is: ${project.x} where x can be a child tag at any depth, or ${x} where x is found at project.properties.x.
        Entries with unresolved properties are not included in the returned list. In the case of chained properties,
        only the top most property is evaluated.
        """
        resolved_values = []
        for value in values:
            replacements: list = []
            # Calculate replacements - matches any number of ${...} entries in the current value
            for match in re.finditer("\\$\\{[^}]+}", value):
                text = match.group().replace("$", "").replace("{", "").replace("}", "")
                if text.startswith("project."):
                    text = text.replace("project.", "")
                else:
                    text = f"properties.{text}"
                # Call find_scm with property resolution flag set to False to prevent the possibility of endless looping
                result = self._find_scm(pom, [text], False)
                if not result:
                    break
                replacements.append([match.start(), result[0], match.end()])

            # Apply replacements in reverse order
            # E.g.
            # git@github.com:owner/project${javac.src.version}-${project.inceptionYear}.git
            # ->
            # git@github.com:owner/project${javac.src.version}-2023.git
            # ->
            # git@github.com:owner/project1.8-2023.git
            for replacement in reversed(replacements):
                value = f"{value[:replacement[0]]}{replacement[1]}{value[replacement[2]:]}"

            resolved_values.append(value)

        return resolved_values
