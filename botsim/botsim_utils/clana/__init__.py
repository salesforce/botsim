"""Get the version."""

#  Copyright (c) 2022, salesforce.com, inc.
#   All rights reserved.
#   SPDX-License-Identifier: BSD-3-Clause
#   For full license text, see the LICENSE file in the repo root or https://opensource.org/licenses/BSD-3-Clause

# Third party
import pkg_resources

try:
    __version__ = pkg_resources.get_distribution("clana").version
except pkg_resources.DistributionNotFound:
    __version__ = "not installed"
