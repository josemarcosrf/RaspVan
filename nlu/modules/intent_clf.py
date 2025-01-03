import logging
import os
import pickle
from typing import List, Optional

import numpy as np
import spacy
from sklearn.metrics import classification_report
from sklearn.preprocessing import LabelEncoder
from sklearn.svm import SVC

from common.utils.io import init_logger

logger = logging.getLogger(__name__)
init_logger(level=os.getenv("LOG_LEVEL", logging.INFO), logger=logger)


class IntentPredictor:
    DEFAULT_SPACY_VEC_MODEL = "en_core_web_sm"

    def __init__(
        self, nlp: Optional[spacy.language.Language] = None, C: int = 3
    ) -> None:
        # Load the spacy vectorizer model
        if nlp is not None:
            self.nlp_vec = nlp
        else:
            logger.info("Loading spacy vectorizer...")
            self.nlp_vec = spacy.load(self.DEFAULT_SPACY_VEC_MODEL)

        # Calculate the dimensionality of nlp
        self.embedding_dim = self.nlp_vec.vocab.vectors_length
        logger.info(f"Embedding dimension: {self.embedding_dim}")

        # Instantiate labelencoder object
        self.le = LabelEncoder()

        # Instantiate SVM classifier
        self.clf = SVC(C=C, probability=True)

    @classmethod
    def from_pretrained(
        cls, clf_pkl: str, le_pkl: str, nlp: Optional[spacy.language.Language] = None
    ):
        ip = cls(nlp=nlp)

        logger.info(f"Loading label encoder ({le_pkl})")
        with open(le_pkl, "rb") as f:
            ip.le = pickle.load(f)

        logger.info(f"Loading Intent classifier ({clf_pkl})")
        with open(clf_pkl, "rb") as f:
            ip.clf = pickle.load(f)

        return ip

    def _encode(
        self, sentences: List[str], labels: Optional[List[str]] = None
    ) -> List[np.ndarray]:
        x_vecs = [self.nlp_vec(sent).vector for sent in sentences]
        if labels is not None:
            return x_vecs, self.le.transform(labels)

        return x_vecs

    def fit(self, sentences: List[str], labels: List[str]):
        logger.info(f"Training on {len(sentences)} intent examples...")
        # Train the label encoder
        self.le.fit(labels)
        # Sentence & Label encoding
        x_vecs, y_indices = self._encode(sentences, labels)
        # Train the SVM classifier
        self.clf.fit(x_vecs, y_indices)

    def predict(self, sentences: List[str]):
        x_vecs = self._encode(sentences)
        intent_preds = self.clf.predict(x_vecs)
        intent_probs = self.clf.predict_proba(x_vecs)

        return [
            {"label": self.le.inverse_transform([lbl_idx])[0], "score": scores[lbl_idx]}
            for lbl_idx, scores in zip(intent_preds, intent_probs)
        ]

    def eval(self, sentences: List[str], labels: List[str]):
        logger.info(f"Evaluating on {len(sentences)} intent examples...")
        # Sentence & Label encoding
        x_vecs, y_true = self._encode(sentences, labels)
        y_pred = self.clf.predict(x_vecs)
        # Classification report
        print(classification_report(y_true, y_pred, target_names=self.le.classes_))
