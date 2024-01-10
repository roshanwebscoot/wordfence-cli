from typing import Optional
from pathlib import Path

from ..util.io import pathlib_resolve, iterate_files
from ..logging import log
from ..api import noc1
from ..api.exceptions import ApiException
from .identifier import FileIdentifier, FileType, FileIdentity, \
    KnownFileIdentity, GroupIdentity


class RemediationSource:

    def get_correct_content(
                self,
                identity: KnownFileIdentity
            ) -> Optional[bytes]:
        pass


class Noc1RemediationSource(RemediationSource):

    def __init__(self, client: noc1.Client):
        self.client = client

    def get_correct_content(
                self,
                identity: KnownFileIdentity
            ) -> Optional[bytes]:
        try:
            type = identity.type.value
            path = str(identity.local_path)
            if identity.extension is None:
                return self.client.get_wp_file_content(
                        type,
                        path,
                        identity.site.get_version(),
                    )
            else:
                return self.client.get_wp_file_content(
                        type,
                        path,
                        identity.site.get_version(),
                        identity.extension.get_name(),
                        identity.extension.version
                    )
        except ApiException as e:
            log.warning(
                    f'Unable to fetch correct content for {identity} - {e}'
                )
            return None


class RemediationResult:

    def __init__(
                self,
                path: Path,
                identity: FileIdentity,
                known: bool = False,
                remediated: bool = False,
                target_path: Optional[Path] = None
            ):
        self.path = path
        self.identity = identity
        self.known = known
        self.remediated = remediated
        self.target_path = target_path if target_path is not None else path

    def __bool__(self) -> bool:
        return self.remediated


class Remediator:

    def __init__(self, source: RemediationSource):
        self.identifier = FileIdentifier()
        self.source = source
        self.input_count = 0

    def get_correct_content(self, identity: KnownFileIdentity) -> bytes:
        return self.source.get_correct_content(identity)

    def remediate_file(
                self,
                path: Path,
                target_path: Optional[Path] = None
            ) -> RemediationResult:
        identity = self.identifier.identify(path)
        result = RemediationResult(path, identity, target_path=target_path)
        if identity.type is FileType.UNKNOWN:
            log.warning(f'Unable to identify {path}')
            return result
        log.debug(f'Identified {path} as {identity}')
        correct_content = self.get_correct_content(identity)
        if correct_content is None:
            log.warning(
                    f'Unable to determine correct content for {identity}, '
                    'skipping remediation...'
                )
            return result
        result.known = True
        try:
            log.debug(f'Overwriting {path}...')
            with open(path, 'wb') as file:
                file.write(correct_content)
            result.remediated = True
        except OSError as error:
            log.error(
                    f'An error occurred while attempting to remediate {path}: '
                    + str(error)
                )
        return result

    def handle_symlink_loop(self, path: str) -> None:
        log.warning(f'Symlink loop detected at {path}')

    def remediate(self, path: str) -> RemediationResult:
        self.input_count += 1
        path = pathlib_resolve(path)
        if path.is_dir():
            file_found = False
            for file in iterate_files(
                        path,
                        loop_callback=self.handle_symlink_loop
                    ):
                yield self.remediate_file(pathlib_resolve(file), path)
                file_found = True
            if not file_found:
                yield RemediationResult(
                        path,
                        GroupIdentity(FileType.UNKNOWN, path)
                    )
        else:
            yield self.remediate_file(path)
