#  Copyright (c) 2022, salesforce.com, inc.
#   All rights reserved.
#   SPDX-License-Identifier: BSD-3-Clause
#   For full license text, see the LICENSE file in the repo root or https://opensource.org/licenses/BSD-3-Clause

from botsim.modules.generator.generator_base import GeneratorBase
from botsim.platforms.botbuilder.parser import EinsteinBotMetaDataParser
from botsim.botsim_utils.utils import seed_everything

seed_everything(42)


class Generator(GeneratorBase):
    """
    Generator implementation for Einstein BotBuilder
    """

    def __init__(self,
                 parser_config={},
                 num_t5_paraphrases=0,
                 num_pegasus_paraphrases=0,
                 num_goals_per_intent=500):
        super().__init__(parser_config, num_t5_paraphrases, num_pegasus_paraphrases, num_goals_per_intent)
        self.parser = EinsteinBotMetaDataParser(parser_config)
        self.parser_config = parser_config
