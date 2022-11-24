#  Copyright (c) 2022, salesforce.com, inc.
#   All rights reserved.
#   SPDX-License-Identifier: BSD-3-Clause
#   For full license text, see the LICENSE file in the repo root or https://opensource.org/licenses/BSD-3-Clause

import os

from botsim.modules.remediator.Remediator import Remediator
from botsim.botsim_utils.utils import dump_json_to_file
from botsim.cli.utils import load_simulation_config, set_default_simulation_intents, get_argparser

if __name__ == "__main__":

    args = get_argparser().parse_args()

    config = load_simulation_config(args.platform, args.test_name)
    if len(config["remediator"]["dev_intents"]) == 0:
        set_default_simulation_intents(config, "remediator")

    report = Remediator.analyze_and_remediate(config)
    path = "data/bots/{}/{}/".format(config["platform"], config["id"])
    if not os.path.isdir(path):
        os.makedirs(path)
    aggregated_report_path = path + "aggregated_report.json"
    dump_json_to_file(aggregated_report_path, report)
