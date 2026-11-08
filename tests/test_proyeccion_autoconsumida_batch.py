import json
import tempfile
import unittest
from pathlib import Path

from calculo_autoconsumida_v0 import calcular_proyeccion_autoconsumida_batch


class ProyeccionAutoconsumidaBatchTests(unittest.TestCase):
    def _create_batch_inputs(self, directory: Path) -> None:
        (directory / "pvgis_indextime_spain.txt").write_text(
            "0001;10\n0002;10\n", encoding="utf-8"
        )
        for cups, consumption in (("CUPS-A", 1), ("CUPS-B", 3)):
            (directory / f"{cups}_2025_01_2025_01.json").write_text(
                json.dumps(
                    [
                        {
                            "cups": cups,
                            "date": "2025/01/01",
                            "time": "00:00",
                            "consumptionKWh": consumption,
                        },
                        {
                            "cups": cups,
                            "date": "2025/01/01",
                            "time": "01:00",
                            "consumptionKWh": consumption,
                        },
                    ]
                ),
                encoding="utf-8",
            )
            (directory / f"{cups}_8760_poruno_2025.txt").write_text(
                f"{cups};0001;0.2\n{cups};0002;0.2\n",
                encoding="utf-8",
            )

    def test_calculates_each_user_against_shared_pvgis_and_aggregates_by_year(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            directory = Path(temp_dir)
            self._create_batch_inputs(directory)

            result = calcular_proyeccion_autoconsumida_batch(
                str(directory)
            )
            saved = json.loads(
                (directory / "trasposición_calculo_autoconsumida.json").read_text(
                    encoding="utf-8"
                )
            )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["usuarios_procesados"], 2)
        self.assertEqual(
            [user["cups"] for user in result["resultados_por_usuario"]],
            ["CUPS-A", "CUPS-B"],
        )
        first, second = result["resultados_por_usuario"]
        self.assertEqual(first["horas_incluidas"], 2)
        self.assertEqual(first["missing_pvgis"], 0)
        self.assertEqual(first["missing_coef"], 0)
        self.assertAlmostEqual(first["energia_exportada"], 2)
        self.assertAlmostEqual(first["energia_autoconsumida"], 2)
        self.assertAlmostEqual(first["energia_importada"], 0)
        self.assertAlmostEqual(second["energia_exportada"], 0)
        self.assertAlmostEqual(second["energia_autoconsumida"], 4)
        self.assertAlmostEqual(second["energia_importada"], 2)
        self.assertEqual(
            result["totales_comunidad_por_anio"]["2025"],
            {
                "energia_exportada": 2,
                "energia_autoconsumida": 6,
                "energia_importada": 2,
            },
        )
        self.assertEqual(saved, result)

    def test_missing_user_coefficient_fails_without_writing_partial_output(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            directory = Path(temp_dir)
            self._create_batch_inputs(directory)
            (directory / "CUPS-B_8760_poruno_2025.txt").unlink()

            with self.assertRaisesRegex(FileNotFoundError, "CUPS-B"):
                calcular_proyeccion_autoconsumida_batch(str(directory))

            self.assertFalse(
                (directory / "trasposición_calculo_autoconsumida.json").exists()
            )

    def test_fixed_coefficients_use_csv_without_poruno_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            directory = Path(temp_dir)
            self._create_batch_inputs(directory)
            for cups in ("CUPS-A", "CUPS-B"):
                (directory / f"{cups}_8760_poruno_2025.txt").unlink()
            (directory / "cups_list_coeficientes.csv").write_text(
                "cups,cif,coeficientes\n"
                "CUPS-A,CIF-A,0.2\n"
                "CUPS-B,CIF-B,0.5\n",
                encoding="utf-8",
            )

            result = calcular_proyeccion_autoconsumida_batch(
                str(directory), metodo_coeficientes="fijo"
            )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["metodo_coeficientes"], "fijo")
        first, second = result["resultados_por_usuario"]
        self.assertAlmostEqual(first["energia_exportada"], 2)
        self.assertAlmostEqual(first["energia_autoconsumida"], 2)
        self.assertAlmostEqual(second["energia_exportada"], 4)
        self.assertAlmostEqual(second["energia_autoconsumida"], 6)
        self.assertEqual(
            result["totales_comunidad_por_anio"]["2025"],
            {
                "energia_exportada": 6,
                "energia_autoconsumida": 8,
                "energia_importada": 0,
            },
        )

    def test_fixed_coefficients_accept_decimal_comma_values(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            directory = Path(temp_dir)
            self._create_batch_inputs(directory)
            (directory / "cups_list_coeficientes.csv").write_text(
                "cups,cif,coeficientes\n"
                "CUPS-A,CIF-A,'0,2'\n"
                'CUPS-B,CIF-B,"0,5"\n',
                encoding="utf-8",
            )

            result = calcular_proyeccion_autoconsumida_batch(
                str(directory), metodo_coeficientes="fijo"
            )

        self.assertEqual(result["status"], "ok")
        first, second = result["resultados_por_usuario"]
        self.assertAlmostEqual(first["energia_exportada"], 2)
        self.assertAlmostEqual(second["energia_exportada"], 4)

    def test_fixed_coefficients_reject_unexpected_extra_fields(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            directory = Path(temp_dir)
            self._create_batch_inputs(directory)
            (directory / "cups_list_coeficientes.csv").write_text(
                "cups,cif,coeficientes\n"
                "CUPS-A,CIF-A,0.2,extra\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "Formato inválido"):
                calcular_proyeccion_autoconsumida_batch(
                    str(directory), metodo_coeficientes="fijo"
                )

    def test_fixed_coefficients_require_a_value_for_each_cups(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            directory = Path(temp_dir)
            self._create_batch_inputs(directory)
            (directory / "cups_list_coeficientes.csv").write_text(
                "cups,cif,coeficientes\nCUPS-A,CIF-A,0.2\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "CUPS-B"):
                calcular_proyeccion_autoconsumida_batch(
                    str(directory), metodo_coeficientes="fijo"
                )

    def test_fixed_coefficients_require_the_csv_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            directory = Path(temp_dir)
            self._create_batch_inputs(directory)

            with self.assertRaisesRegex(FileNotFoundError, "cups_list_coeficientes.csv"):
                calcular_proyeccion_autoconsumida_batch(
                    str(directory), metodo_coeficientes="fijo"
                )

    def test_fixed_coefficients_reject_non_finite_values(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            directory = Path(temp_dir)
            self._create_batch_inputs(directory)
            (directory / "cups_list_coeficientes.csv").write_text(
                "cups,cif,coeficientes\n"
                "CUPS-A,CIF-A,nan\n"
                "CUPS-B,CIF-B,0.5\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "Coeficiente inválido"):
                calcular_proyeccion_autoconsumida_batch(
                    str(directory), metodo_coeficientes="fijo"
                )

    def test_rejects_unknown_coefficient_method(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            directory = Path(temp_dir)
            with self.assertRaisesRegex(ValueError, "metodo_coeficientes"):
                calcular_proyeccion_autoconsumida_batch(
                    str(directory), metodo_coeficientes="automatico"
                )

    def test_rejects_output_path_outside_input_directory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            directory = Path(temp_dir)
            self._create_batch_inputs(directory)

            with self.assertRaisesRegex(ValueError, "permanecer dentro"):
                calcular_proyeccion_autoconsumida_batch(
                    str(directory),
                    output_file="../outside.json",
                )


if __name__ == "__main__":
    unittest.main()
