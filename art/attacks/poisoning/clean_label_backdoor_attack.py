# MIT License
#
# Copyright (C) The Adversarial Robustness Toolbox (ART) Authors 2020
#
# Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated
# documentation files (the "Software"), to deal in the Software without restriction, including without limitation the
# rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit
# persons to whom the Software is furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all copies or substantial portions of the
# Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE
# WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT,
# TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
"""
This module implements Backdoor Attacks to poison data used in ML models.
"""
from __future__ import absolute_import, division, print_function, unicode_literals

import logging
import numpy as np

from typing import Optional, Tuple, TYPE_CHECKING, Union

from art.attacks import PoisoningAttackBlackBox
from art.attacks.evasion import ProjectedGradientDescent
from art.attacks.poisoning import PoisoningAttackBackdoor
from art.estimators.classification.classifier import ClassifierLossGradients

if TYPE_CHECKING:
    from art.utils import CLASSIFIER_LOSS_GRADIENTS_TYPE


logger = logging.getLogger(__name__)


class PoisoningAttackCleanLabelBackdoor(PoisoningAttackBlackBox):
    """
    Implementation of Clean-Label Backdoor Attacks introduced in Gu, et. al. 2017

    Applies a number of backdoor perturbation functions and switches label to target label

    | Paper link: https://arxiv.org/abs/1708.06733
    """

    attack_params = PoisoningAttackBlackBox.attack_params + ["backdoor", "proxy_classifier", "target", "pp_poison",
                                                             "norm", "eps", "eps_step", "max_iter", "num_random_init"]
    _estimator_requirements = ()

    def __init__(self,
                 backdoor: PoisoningAttackBackdoor,
                 proxy_classifier: "CLASSIFIER_LOSS_GRADIENTS_TYPE",
                 target: np.ndarray,
                 pp_poison: float = 0.33,
                 norm: Union[int, float, str] = np.inf,
                 eps: float = 0.3,
                 eps_step: float = 0.1,
                 max_iter: int = 100,
                 num_random_init: int = 0,
                 ) -> None:
        """
        Creates a new Clean Label Backdoor poisoning attack

        :param backdoor: the backdoor chosen for this attack
        :param proxy_classifier: the classifier for this attack ideally it solves the same or similar classification
                                 task as the original classifier
        :param target: The target label to poison
        :param pp_poison: The percentage of the data to poison. Note: Only data within the target label is poisoned
        :param norm: The norm of the adversarial perturbation supporting "inf", np.inf, 1 or 2.
        :param eps: Maximum perturbation that the attacker can introduce.
        :param eps_step: Attack step size (input variation) at each iteration.
        :param max_iter: The maximum number of iterations.
        :param num_random_init: Number of random initialisations within the epsilon ball. For num_random_init=0 starting
                                at the original input.
        """
        super().__init__()
        self.backdoor = backdoor
        self.proxy_classifier = proxy_classifier
        self.target = target
        self.pp_poison = pp_poison
        self.attack = ProjectedGradientDescent(proxy_classifier,
                                               norm=norm,
                                               eps=eps,
                                               eps_step=eps_step,
                                               max_iter=max_iter,
                                               targeted=False,
                                               num_random_init=num_random_init)
        self._check_params()

    def poison(
        self, x: np.ndarray, y: Optional[np.ndarray] = None, broadcast=False, **kwargs
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Calls perturbation function on input x and returns the perturbed input and poison labels for the data.

        :param x: An array with the points that initialize attack points.
        :param y: The target labels for the attack.
        :param broadcast: whether or not to broadcast single target label
        :return: An tuple holding the `(poisoning_examples, poisoning_labels)`.
        """
        data = np.copy(x)
        estimated_labels = self.proxy_classifier.predict(data) if y is None else np.copy(y)

        # Selected target indices to poison
        all_indices = np.arange(len(data))
        target_indices = all_indices[np.all(estimated_labels == self.target, axis=1)]
        num_poison = int(self.pp_poison * len(target_indices))
        selected_indices = np.random.choice(target_indices, num_poison)

        # Run untargeted PGD on selected points, making it hard to classify correctly
        perturbed_input = self.attack.generate(data[selected_indices])

        # Add backdoor and poison with the same label
        poisoned_input, _ = self.backdoor.poison(perturbed_input, self.target, broadcast=True)
        data[selected_indices] = poisoned_input

        return data, estimated_labels

    def _check_params(self) -> None:
        if not isinstance(self.backdoor, PoisoningAttackBackdoor):
            raise ValueError("Backdoor must be of type PoisoningAttackBackdoor")
        if not isinstance(self.attack, ProjectedGradientDescent):
            raise ValueError("There was an issue creating the PGD attack")
        if not 0 < self.pp_poison < 1:
            raise ValueError("pp_poison must be between 0 and 1")